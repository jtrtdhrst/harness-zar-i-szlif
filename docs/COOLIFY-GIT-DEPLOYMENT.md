# Coolify ↔ harness-zar-i-szlif | source binding and safe cutover

Verified on 2026-11-01. The machine-readable source map is [coolify-source-bindings.json](./coolify-source-bindings.json). This is **not** proof of applied source bindings.

## Current blockers (confirmed in live APIs)

- Coolify GitHub App `coolify-zar-i-szlif` (ID 1) lists only `miloszspyrka-code/zar-i-szlif`. It **cannot read** private `miloszspyrka-code/harness-zar-i-szlif`. Grant that repository to the existing GitHub App installation in [GitHub Installed Apps](https://github.com/settings/installations). Do not make the repository public, create shared PATs or copy secrets into Compose.
- All nine MCP workloads below currently run from prebuilt **image-only Compose services** with no git source. Updating `watch_paths` on an image-only service does not turn it into a Git build. Coolify GitHub App access and a Git-backed candidate app are both required.
- GitHub Actions are intentionally disabled. Do not enable them silently; Coolify native GitHub webhook/branch path filtering is the intended mechanism.
- `hermes-gateway-poc-v2` is inline-Dockerfile based, with misleading `coollabsio/coolify` Git metadata. The harness repository has no buildable Hermes Gateway source folder: do **not** auto-deploy that service from the harness root.
- `hermes-paperclip-sync-checks` reads host-mounted scripts and an Alpine image; it is not a Git deployment and its green smoke check must not stand in for real Paperclip→Hermes→Wiki/Skills→Hindsight→Opik E2E.
- The panel `zar-i-szlif-web` belongs to the OTHER repo, has a stable release branch and a deliberately paused watch path; don't rewire it into harness.

## Verified isolated build candidates

| Current Coolify service | Build context | Dockerfile | Watch path | Notes |
|---|---|---|---|---|
| paperclip-mcp | `/paperclip-mcp` | `/Dockerfile` | `paperclip-mcp/**` | Preserve Paperclip core and existing MCP state |
| plasmic-mcp | `/plasmic-mcp` | `/Dockerfile` | `plasmic-mcp/**` | Requires exact secrets and persistent state mapping |
| comfy-mcp | `/comfyui-mcp` | `/Dockerfile` | `comfyui-mcp/**` | Legacy combined source until engine/MCP split is complete |
| mantic-mcp | `/mantic-mcp` | `/Dockerfile.http` | `mantic-mcp/**` | Current resource lives under Mautic project; no automatic move |
| emailens-mcp | `/emailens-mcp` | `/Dockerfile` | `emailens-mcp/**` | Stateless candidate |
| playwright-mcp | `/playwright-mcp` | `/Dockerfile` | `playwright-mcp/**` | Existing container under Kod MCP project |
| qdrant-mcp | `/qdrant-mcp` | `/Dockerfile` | `qdrant-mcp/**` | NEVER build/deploy its bundled Compose database; MCP only |
| supabase-mcp | `/supabase-mcp` | `/Dockerfile` | `supabase-mcp/**` | Preserve target Supabase URL/auth, no second Supabase instance |
| ubuntu-mcp | `/ubuntu-mcp` | `/Dockerfile` | `ubuntu-mcp/**` | Privileged SSH bridge: ensure auth, no public anonymous entrypoint |

All nine Dockerfiles passed `docker buildx build --check` against the exact `main` tree SHA `06c83ec0bbc38a2a59a348c6856519f5ba41b0a7`. Three isolated canary images also built successfully: `ubuntu-mcp` (confirmed `mcp-ssh-manager=3.8.6`), `emailens-mcp` (`bridge.mjs` present) and `mantic-mcp` (`bridge/bridge.mjs` present). The probes used `--network none` and no production secrets. **These checks do not prove all 9 full builds or real authenticated MCP E2E**.

## Systematic migration / auto-deploy gate

1. **Source permission**: grant the existing Coolify GitHub App access to private harness repo, then verify `github_apps(list_repos)` shows it. A successful GitHub connector read does NOT prove the Coolify App can read it.
2. **Candidate, not production cutover**: for each code-bearing MCP, create a separate Coolify GitHub-backed application candidate in the correct project/environment, using the exact branch `main`, base directory and Dockerfile above. Keep `instant_deploy=false` until env, secret refs, port, network aliases and persistent mounts are reconciled. Do not create duplicate production DNS targets.
3. **Build gate**: build candidate, verify exact immutable commit SHA, scan startup/health logs, test representative MCP `initialize`, `tools/list`, and at least one authorized `tools/call`, and denial of unauthorized calls. Preserve exposed ports and bind mounts; for Ubuntu, use separate controlled test auth.
4. **Cutover gate**: independent CTO review of scope and rollback, then controlled route change. Verify requests and state. Do not delete old Compose resources, volumes or images until rollback is proven. Never mount another project's private volume into a cross-project service.
5. **Enable native webhook auto-deploy** ONLY when the candidate has passed and is the approved active source. Use folder-only `watch_paths`; changes to other folders must not trigger a build. Require a smoke commit changing ONLY this folder (non-secret comment or test); read back a new Coolify deployment with `is_webhook=true`, matching git SHA and successful health+MCP tests; prove another folder change yields no deployment.
6. **Revert safety**: simulate rollback to previous digest and verify health/data before closing issue. Store redacted evidence under the owning Paperclip release issue.
7. **Operating model**: CHO coordinates the work. Harness Engineer handles reproducible source mapping, Delivery & Release Manager owns approved Git/PR/release transition, CTO independently reviews. Use the existing Paperclip issues (especially KOMAA-1497); do not start another task tree or bypass blocked reviews.

## Exclusions

The following are metadata / pinned upstream-image services, **not Git-built from README folders**: Paperclip Core, Mautic, Supabase, Qdrant, Opik, Opik MCP, Coolify MCP, Comfy runtime, cloudflared ingress. Plasmic Studio has an actual Compose source but must be handled as a separate stateful migration with preserved Postgres and secrets. `mcp-edge` is a legacy candidate without a matching active service and should not be deployed simply because the folder exists.

## Acceptance (must fail closed)

- GitHub App can read the exact private source repository.
- Each authorized application has the exact `git_repository`, `git_branch`, `base_directory`, `dockerfile_location`, and `watch_paths` read back.
- Every new Docker image is built from an immutable source SHA, passes health and an authorized MCP call, with no secret leakage.
- A folder-local Git push triggers only its matching app; an unrelated folder push triggers none.
- Production stateful volumes and DNS untouched until controlled cutover; rollback proof and CTO review captured.
- A red/blocked integration must not be disguised as green by a healthy container or passing Dockerfile lint.

Documentation: [Coolify automatic deployments](https://coolify.io/docs/applications/deployments/automatic-deployments), [GitHub integration](https://coolify.io/docs/applications/sources/github/auto-deploy), [Compose services](https://coolify.io/docs/services/configuration/docker-compose).
