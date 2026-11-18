# RepoWise deployment writer — Git/Coolify release contract

Owner: ZARI-240. Existing source: `ops/repowise/deployment_evidence_mcp.py`.
This package **does not** authorize independent deployment or bypass ZARI-213.

## Reviewed build path

- `Dockerfile.publisher`: Python 3.12 image, pinned RepoWise 0.60.1 / MCP
  1.30.0, git and CA certificates, nonroot UID 999, no build-time secrets.
  Docker **build fails** if `test_deployment_evidence_mcp.py` fails.
- `compose.publisher.yaml`: Git-backed Coolify app, no public domain.
  First deploy on host loopback **7342**, leaving existing vetted
  operator writer **7339** untouched.
- Review and CI must bind exact Git PR head SHA. Image digest and actual
  Coolify UUID must be recorded separately; they are never inferred from
  source SHA or a green CI result.

## Required runtime inputs (provide through Coolify, not Git)

`REPOWISE_PRODUCT_HOST_PATH` points to the existing read-only Product Git
checkout; `REPOWISE_EPISODES_HOST_PATH` points to the nested native
`.repowise/episodes` directory (only permitted write mount);
`REPOWISE_SYNC_LOCK_HOST_PATH` is the existing advisory sync lock file;
`REPOWISE_TOKEN_FILE_HOST_PATH` is the protected token **file path**
(not its contents). `REPOWISE_WRITER_PORT` defaults to staging 7342.
All host paths must exist and be owner-authorized. Do not set a public domain.

The actual bearer must stay in a root-managed directory as a mode-0600
regular file **owned by service UID:GID 999:999**, so the nonroot image can
read it via a read-only bind. Root administers the mount path and can revoke it;
the secret's inode is not root-owned. Never put token values in Git, issues,
logs or plain Compose env. A root:root 0600 file would be unreadable by UID 999
and is an invalid staging configuration, not a reason to widen permissions. The writer must not run as root and
may never mount Product `.git` writable. The host path for Product
must be RO and only episodes nested bind RW. The existing sync timer
remains the only indexer; publisher shares its exact lock inode.

## Acceptance gates

1. Validate `docker compose config --quiet` with dummy paths and
   build the exact reviewed source; all native MCP tests PASS in-image.
2. Create a new Coolify resource from the private Harness GitHub App
   with source SHA + Compose path and auto-deploy initially **off**.
   Preserve / record UUID, server, environment, build id, image digest.
3. Stage at 7342 while manual 7339 stays live. Inspect running
   container `user=999:999`, `CapDrop=ALL`, root FS read-only,
   no public URL and exact RO/RW mounts. Unauthorized `/mcp`
   returns 401, authenticated Streamable HTTP protocol passes.
4. Conduct bounded agent `tool_use` and `tool_result` on the
   newly built **staging** MCP. Verify Product exact source SHA and
   cross-repo denial. Existing ZARI-256 tests prove the preexisting
   manual writer only, not this build.
5. Explicitly approve a cutover, change the Multica server URL using
   a mode-0600 local config file with no token logging, then verify
   another real native agent write/read/negative. Only then stop
   legacy operator container. Observe health and exact digest.
6. Rollback: restore previous Multica MCP server definition, restart
   previously retained operator container, and stop the new instance.
   Preserve immutable evidence and check a 401 negative before recovery
   is declared. Never erase existing episodes or turn off RepoWise sync.

## E2E statuses

`SOURCE_REVIEW`, `IMAGE_BUILD_TESTS`, `COOLIFY_STAGING`,
`AGENT_WRITER_TOOL_USE`, `PRODUCTION_CUTOVER`, `ROLLBACK` must be
independently PASS/FAIL/NOT_RUN. A native episode marked
`PARTIAL_LIVE_OBSERVED` is *not* deployment acceptance. Full
ZARI-240 Done requires authorized reviewed service deploy, digest
attestation, independent authenticated QA and rollback — in addition
to ZARI-213 isolation protections.

## Coolify host-volume validation — confirmed 2026-11-18

The initial Git-backed staging app `gl8bvfjtw2af8hkox4mguzzr` rejected
`compose.publisher.yaml` **before building**, because Coolify's Compose
security parser disallows `${...}` substitution in the `volumes[].source`
field (deployment `fdl8ixqv6ydb0qcxnrjchpvl`, status FAILED).
Do not disable the validator, enable raw Compose bypass, or make the
Product Git mount writable to get around this check.

Use `compose.publisher.coolify.yaml` for this specific verified VPS:
all four bind sources are static and match preflight readback of the
already running operator writer. No bearer content is in Git; the
root-controlled mode-0600 file itself remains a read-only bind.
The portable `compose.publisher.yaml` remains available for local
`docker compose config` and repeatable source tests.

For the staging app, pin the exact reviewed source SHA and set
`docker_compose_location=/ops/repowise/compose.publisher.coolify.yaml`.
Keep auto-deploy and preview deploys disabled; retain no public domain,
loopback port 7342 and the existing independent writer at 7339.
Verify `docker compose config --quiet`, Coolify's runtime status,
actual image digest, mounts, 401 without bearer and authenticated
native MCP read/negative tool results before any cutover.
The new app has NO release authority while ZARI-213 and parent
ZARI-240 controls remain unproven; no rollback or production QA claim
follows from successfully creating this application.

### Live host identity / ACL proof, 2026-11-18 (no token contents read)

Exact UID-999 non-secret canary on the existing manual writer container
`repowise-deployment-publisher-product` using `docker exec --user 999:999`
opened `/run/secrets/repowise-token` with `os.open(O_RDONLY|O_NOFOLLOW)`,
returned **PASS**, `fileuid=999`, `mode=0600`, `regular=True`;
`/run/lock/repowise-github-sync.lock` opened the same way **PASS**
(`uid=0,mode=0640`, explicit existing read ACL for the mapped UID 999).
No token bytes were read. Actual host token path
`/etc/repowise-publisher/product.token` is a regular, non-symlink file
(`uid=999,gid=999,mode=0600`). Host Product directory and episodes directory
are canonical, non-symlink paths owned by UID 999; the lock and token source
also resolve canonically without symlinks. All four mounts are already present
on the independently running manual service. Their actual functionality does
not by itself prove a newly built Coolify staging instance is started, and
must be checked again on that instance's newly built image before cutover.

Unauthorized HTTP on manual writer port 7339 remains 401. The original failed
Coolify staging attempt used the portable Compose and created NO runtime;
new staging build/test/startup at port 7342 and digest/rollback remain pending
independent approval. The owner of the *file* must not be confused with the
operator who administratively manages the protected path.

## Verified Git-backed staging and auto-deploy trigger — 2026-11-18

The following updates supersede the earlier *pending staging* paragraphs above. They are scoped to the staging resource, **not** the public product or any on-HOLD MCP lane.

- GitHub PR #143, exact reviewed head `70680ed51ddc881d39451361b67593c8da788bbe`, merged to `main` as `60ba36da0639e9b4f41d9b3b9b82dd034ff57c00`. Release Lanes Policy CI succeeded.
- Coolify staging application `gl8bvfjtw2af8hkox4mguzzr`, deployment `srunxs6dorobgnwabtqkwq2n`, source `60ba36da0639e9b4f41d9b3b9b82dd034ff57c00`, status `finished`; resulting image digest `sha256:c86cee0d5fd4c5f478887b13152a27753d402e6fd5f1d8702b6432104a311191`, container health `healthy`, running UID:GID `999:999` on loopback `127.0.0.1:7342`.
- Staging MCP negative tests: absent/bad bearer => HTTP 401; valid bearer => `initialize`, `tools/list` and read-only `get_deployment_observation` PASS. Existing production writer on 7339 is left running independently.
- Coolify staging setting is now `is_auto_deploy_enabled=true` with `watch_paths=ops/repowise/**`; a path matcher probe accepts `ops/repowise/Dockerfile.publisher` and rejects `plasmic-mcp/services/plasmic-mcp/server.ts`. This enables the GitHub App push trigger only for staging, not global release authorization.
- **Still required:** real GitHub push webhook -> new Coolify deployment ID -> exact new main SHA -> running digest and authenticated smoke. The documentation commit that adds this section is an intentional watched-path E2E canary; do not declare this gate PASS before a subsequent webhook-triggered deploy is observed (`is_webhook=true` and `is_api=false`).
- **Out of scope:** auto-promoting held services, reissuing expired production grants, or moving the Multica writer endpoint without an independent QA and rollback proof.
