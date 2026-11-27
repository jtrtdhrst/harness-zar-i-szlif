# RepoWise — Git branch → build → Coolify runtime routing (operator-verified snapshot)

**Scope:** Żar i Szlif / Harness. **Observed:** 2026-11-20 19:24 UTC through authenticated Coolify application/service readback and GitHub repository metadata. **Status:** navigation evidence, **not** a release approval or continuous runtime attestation.

## Rules for every agent (MUST)

1. A **GitHub default branch** is for development/navigation. It is **not** evidence of what production builds. Resolve the actual configured `git_repository`, `git_branch`, `base_directory`, `dockerfile_location`, `build_pack`, `watch_paths`, and `settings.is_auto_deploy_enabled` from the **current Coolify application UUID**.
2. **Git-backed application:** Coolify's configured ref is the **build selector**, not an immutable runtime commit. Resolve its GitHub commit SHA separately, inspect the exact deployment record, and compare with the running container's source revision / image digest. A green healthcheck is not SHA parity.
3. **Compose service / image-pinned lane:** the Docker Compose `image:` reference or immutable digest is the build input. **Do not assign any Git branch** just because a Docker image, service name, Dockerfile or `ops/release-lanes.json` mentions a repository. For a source-built image, require provenance `source_sha → CI/build → digest → Coolify UUID → running digest`; absent evidence => `UNVERIFIED`.
4. **Release policy and inventory differ.** `ops/release-lanes.json` is an authorization / historical inventory manifest (its `scope_snapshot.observed_at` was 2026-11-04). Never use its historical Coolify totals, `observed_baseline`, branch names or `auto_deploy_expected` as a present-day Coolify readback. The validator `scripts/check-release-lanes.py` is a *policy gate*, not a runtime discovery service.
5. **Product integration vs release:** `miloszspyrka-code/zar-i-szlif:main` is the reviewed integration history. `ci-approved` is the separately promoted production release ref. The app `zar-i-szlif-web` **builds from `ci-approved`**, not directly from `main`. Check `/__release.json` + Coolify deployment + running digest before asserting what is live. Product release gate: `scripts/product_native_promotion.py`.
6. **Harness:** `miloszspyrka-code/harness-zar-i-szlif:main` is the primary integration branch. Some applications can intentionally point to a feature branch with a manual HOLD. This does not make that feature branch the canonical source for other services. Harness release controls: `scripts/harness_release_admission.py`, `scripts/harness_delivery_controller.py`, `scripts/harness_native_delivery.py`.
7. **No guessing:** if an agent cannot read an exact Coolify UUID/ref, deployment SHA, image digest or webhook event, say `UNKNOWN / NOT VERIFIED`, identify the missing readback, and do **not** say built, merged, deployed, E2E or auto-deploy completed. Report a current UTC `observed_at` and provenance/source for all assertions.
8. **Freshness:** RepoWise's two indexed code repositories come from GitHub `main` via `repowise-github-sync.timer`. `repowise list_repos` can verify indexed commits. It **cannot** answer live deployment questions by itself. Before a release decision query authenticated Coolify and GitHub; for source-built Compose, verify the running Docker image labels/digest on Ubuntu. A stale or unavailable readback must not be silently replaced with a remembered answer.

## Verified Coolify application routing at observation time

| Coolify application / UUID | Configured Git source | Configured branch | Meaning / caveat |
| --- | --- | --- | --- |
| `zar-i-szlif-web` / `k0vwdsjazxguvgmh4qixjgxn` | `miloszspyrka-code/zar-i-szlif` | `ci-approved` | PROD; promotion from reviewed `main`; web release marker `/__release.json` |
| `zar-i-szlif-mcp-host` / `xevk2uwgf7lgbnflyvwkaoqp` | `miloszspyrka-code/zar-i-szlif` | `ci-approved` | Git-configured; live ingress/runtime identity still needs separate proof |
| `zar-i-szlif-mascot-worker` / `e8rnh91jkim7cladg7lqdmfu` | `miloszspyrka-code/zar-i-szlif` | `ci-approved` | Git-configured worker; requires deployment/digest evidence |
| `github-ops-mcp` / `t09dqe2eppn2eiqmhzlf8xzp` | `miloszspyrka-code/harness-zar-i-szlif` | `feat/github-ops-mcp-20261120` | **Restricted manual HOLD**; not automatically `main` and not authorized to write |
| `hermes-gateway` / `2sganhxhhnioiqh4an9g2f4k` | `miloszspyrka-code/harness-zar-i-szlif` | `main` | Git-configured; whether changes auto-deploy is a separate Coolify setting |
| `multica-mcp` / `5o4edyfjo0wftfg08mtkknir` | `miloszspyrka-code/harness-zar-i-szlif` | `main` | Git-configured; require exact running SHA before success claim |
| `repowise-deployment-publisher-staging` / `gl8bvfjtw2af8hkox4mguzzr` | `miloszspyrka-code/harness-zar-i-szlif` | `main` | Separate staging writer; never confuse with production read-only index |
| `repowise` / `oea9obpkhzbgkmipxwqmz2hj` | `repowise-dev/repowise.git` | `v0.60.1` | Vendor software version; 2 mounted indexed repos are independent |
| `local-build-registry` / `g0xdkztpmjnhgwms7qelzxqd` | Coolify reports `coollabsio/coolify` | `main` | **Metadata only**; verify actual image/Compose before inferring a Git build |
| `zar-i-szlif-image-canary` / `cs847jiwtuq5rlm8ntjeohgf` | Coolify reports `coollabsio/coolify` | `main` | **Image-backed canary**; NOT proof of build from that repo branch |
| `zar-i-szlif-mcp-host-image` / `z4ikllc2j5zvhjr2tyloovmg` | Coolify reports `coollabsio/coolify` | `main` | **Image-backed host**; NOT proof of build from that repo branch |

**Compose services:** On this same readback Coolify returned **25 services**, for example `plasmic-mcp`, `ubuntu-mcp`, `comfy-mcp`, `opik-mcp`, `repowise-mcp-runtime`. Their builds cannot be accurately attributed to GitHub `main` or any other branch using application metadata. Inspect each service's effective Compose `image:`, resolved image digest, container revision label and signed build attestation; missing = `UNVERIFIED`. A 200 / healthy is only a process-health observation.

## Practical source-of-truth decision flow

1. Given a user-facing name, **resolve one Coolify UUID** (current `list_applications` or `list_services`), never name-match two resources into one result.
2. If type=`application`, read `get_application(uuid)`. Take `git_repository` and `git_branch` from **that** record; read `settings.is_auto_deploy_enabled` and `watch_paths` separately. Compare the Git ref SHA with the specific deployment's recorded source SHA.
3. If type=`service`, read `get_service(uuid)` and parse exact `image:` entries; verify Docker `Image`, `RepoDigests`, `org.opencontainers.image.revision` / required attestation. Do not invent a Git branch.
4. Look up actual Coolify deployment ID, result, trigger (`webhook` vs `api` vs manual) and running container digest. For `zar-i-szlif-web`, compare `https://panel.zariszlif.pl/__release.json` with promoted SHA.
5. Compare to GitHub `main`, `ci-approved` or chosen feature ref (as applicable), review/checks and release-gate policy. Distinguish `CONFIGURED`, `BUILT`, `DEPLOYED`, `RUNTIME_VERIFIED`, `PRODUCTION_E2E_PASS`.
6. When facts conflict, **Coolify runtime + GitHub immutable refs** supersede this dated routing snapshot; record the mismatch and fix the corresponding source manifest through reviewed code rather than concealing drift.

**RepoWise MCP query examples**: “Where is the product promotion contract between `main` and `ci-approved`?” can be answered from indexed code. “What exact branch/digest is running in `plasmic-mcp` right now?” needs live Coolify + Docker checks and cannot be answered from RepoWise search alone.

## Related ownership; do not duplicate control planes

- Current historical release policy: `ops/release-lanes.json` and `scripts/check-release-lanes.py`.
- Existing runtime inventory reconciliation: Harness PR **#158** (not automatically merged or live).
- Existing exact Compose MCP routing verification: Harness PR **#182** (check current PR status / head before using).
- Existing RepoWise freshness fix: Harness PR **#130** (check current PR status / head before installing).
- Existing secure index sync: `ops/repowise/repowise_github_sync.sh`, `ops/repowise/README.md`. Do not add a second timer/index writer.
- Build / signed CI / per-service authorization: `scripts/harness_native_delivery.py` and the current reviewed admission mechanism.

**Not established by this document:** deployed source SHAs for all services, CI completeness, automatic build execution, any production test E2E, or permission to merge, delete branches, release services or bypass HOLD. These require live checks.

## Observed Compose service image selectors (2026-11-20 UTC)

These are **configured Coolify service image references**, not an authenticated build history, not Git branches, not verified running digests, and not evidence of a successful automatic release. An image tag containing a commit-like prefix (e.g. `deb907a88591`) is **only a label** until independently bound to a build attestation. Mutable tags (`latest`, `HEAD`) and unresolved `${...}` expressions need special attention. The `*` and `...` notation below abbreviates multi-image stacks; inspect `get_service(uuid)` for complete current lists.

| Compose service | Coolify UUID | Configured image selectors (summary) |
| --- | --- | --- |
| `plasmic` | `mzmlcorgkfgdy44hqfmmtxgw` | `plasmic-studio:2026-11-15-e2e0b744; plasmic-wab:2026-11-15-e2e0b744` |
| `hindsight-core` | `hjda7ckq5z4luhd1vpdepi0r` | `ghcr.io/vectorize-io/hindsight:latest-slim` |
| `hindsight-mcp` | `aglen8ervlo2lpi30oz8iii9` | `caddy:2-alpine` |
| `opik` | `s7a4rwqbij7w4fxlnauriblo` | `ghcr.io/comet-ml/opik/*:2.2.121; zookeeper:3.9.4; clickhouse:26.3.16.16-alpine; MinIO image` |
| `mautic` | `8byf8qjxdixpwp7lsnr8zpto` | `${MAUTIC_IMAGE:-mautic/mautic:7.2.0-20260902-apache} (unresolved Compose fallback; verify effective env)` |
| `supabase` | `r2gnunvpkqwmuew1tupbf7lx` | `upstream Supabase images: storage-api:v1.60.4, gotrue:v2.189.0, postgrest:v14.12, etc.` |
| `opik-mcp` | `egasedqaofxnzcqppuxi805h` | `local/opik-mcp:3.0.7; local/opik-access-guard:20261105-v2; nginx:alpine` |
| `emailens-mcp` | `16qnapdkj0qqqmeokepdechk` | `127.0.0.1:5000/harness-emailens-mcp:deb907a88591` |
| `plasmic-mcp` | `a6ci2beifbinzckfnneiqnjd` | `127.0.0.1:5000/harness-plasmic-mcp:deb907a88591` |
| `coolify-mcp` | `f7smgdueq8frlex9lfhp9iji` | `ghcr.io/stumason/coolify-mcp:3.9.0` |
| `supabase-mcp` | `tjit4c8m0kjh8brkmdhyvkde` | `127.0.0.1:5000/harness-supabase-mcp:deb907a88591` |
| `qdrant` (retained vector DB; not retired MCP) | `eciprwgeyol4znmdd0dpu3xc` | `qdrant/qdrant:1.20.0@sha256:9bfc89f9914fc14876a88c05270685921a55b8877b254a98bcc1cc2f0a424cd2` (historical source inventory) |
| `comfy-mcp` | `kkhfw0napmeaqewgdirwhc1h` | `local/comfyui-mcp:0.52.206-chatfiles7` |
| `opencode` | `26aqp0flyvdinjn6dklxnb1c` | `local/opencode-standalone:2.2.5-custom; alpine/socat` |
| `ubuntu-mcp` | `lcnjb3vreec7saihkhan6akh` | `127.0.0.1:5000/harness-ubuntu-mcp:3c8da46902d2` |
| `comfy` | `hdn0rl4wznbvaoizna61bbyy` | `local/comfyui-cpu:KOMAA1599-fe26d14f; local/comfyui-mcp:0.52.206` |
| `cloudflared-mcp` | `3byzyvjxsycixyzcpxbujzev` | `cloudflare/cloudflared:latest` |
| `mcp-activation` | `ra0iy2xs7abgms1r0phx4iqg` | `sablierapp/sablier@sha256:c24b7198...; tecnativa/docker-socket-proxy@sha256:1f5038b5...` |
| `outline-knowledge` | `g16yynrbdpkab4hnmaoj7vxk` | `docker.getoutline.com/outlinewiki/outline:1.12.0` |
| `mantic-mcp` | `bioufw4uxwuhmr51ueyahf0u` | `127.0.0.1:5000/harness-mantic-mcp:deb907a88591` |
| `playwright-mcp` | `9e4fzsodixl4qzzap4zg0ntp` | `127.0.0.1:5000/harness-playwright-mcp:deb907a88591` |
| `multica-stack` | `6ihjnudsifbcvklz5hqxdldc` | `ghcr.io/multica-ai/multica-backend:v0.8.1; ghcr.io/multica-ai/multica-web:v0.8.1; axllent/mailpit:v1.27.2` |
| `multica-edge` | `vwe5lv4bniosxug34uhyf0ag` | `cloudflare/cloudflared:2026.9.3` |
| `repowise-mcp-runtime` | `lecwi3emh9hjxir7gphmalie` | `fciqzgceop7mqtqickkfomd7:HEAD` |

**Runtime-provenance next check per row:** current effective image ID/digest from Docker, exact built source SHA + CI attestation where applicable, release authorization, Coolify deployment ID, and functional live E2E. Nothing in this table supplies those missing proofs.

## RepoWise retrieval negative control (verified 2026-11-20)

At indexed Harness source SHA `2b1794e00d7fc17568b18b3fcc371a1bc7152bfd`, `get_answer` failed to retrieve the `github-ops-mcp` branch from this markdown file. This is a **retrieval gap**, not missing source. A live `search_codebase(mode="hybrid", query="github-ops-mcp")` returned zero `lines`, while **`query="`github-ops-mcp`"`** returned this file, line 23, with `feat/github-ops-mcp-20261120`. The equivalent backtick-quoted queries for `zar-i-szlif-web` and `multica-mcp` also returned relevant source lines. Querying the exact Coolify UUID `t09dqe2eppn2eiqmhzlf8xzp` likewise returned line 23. `get_context` for this markdown path returns a triage/preview, **not the complete source bytes**.

Agents with authorized access: prefer one **backtick-quoted exact identifier** in `search_codebase`, then check the source's `lines` and indexed SHA; if absent, query the exact current Coolify UUID or read this file from the authorized GitHub exact commit. Never promote a `get_answer` LOW-confidence guess into a branch fact. See existing native Multica skill `repowise-evidence-gate`, section 2a; a skill instruction is not a guaranteed server-side retrieval fix.
