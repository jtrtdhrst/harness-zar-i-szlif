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

The actual bearer must stay in a root-controlled mode-0600 file read by
the nonroot image via a read-only bind; never put tokens in Git, issue
text, logs or plain Compose env. The writer must not run as root and
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
