# Source-only folders and production image builds

Policy (2026-11-09): retain non-MCP sources in this repository for agent and RepoWise context. Source presence does **not** authorize a Docker build, deployment, or Cloudify/Coolify service creation.

## Two distinct operations

1. **Validation**: lint and unit tests may run on scoped source changes; no Docker image build for source-only folders.
2. **Promotion**: for an actively deployed application, build an immutable image **on the self-hosted build runner** after the reviewed source SHA passes CI. Push the immutable image to a registry, then configure Coolify to pull **that exact digest**. Production must not git-clone and build source independently. Confirm running digest, health, endpoint and rollback before success.

Until a registered, online self-hosted runner and registry publication are verified, **do not** change the live production application's source mode to an image mode: that would interrupt existing releases. No claim that the runner or image release is currently operational.

## Classification

Source-only (no automatic image builds solely because they are in Git): `comfy/`, `plasmic/`, `qdrant/`, `supabase/`, `mautic/`, `opik/`, `paperclip/`, `cloudflare-ingress/`, `shared-ingress/`, `_archive/`, `kod-aplikacji/`, `kod-mcp/`, `docs/`.

Standalone MCP sources (`*-mcp/`) are independently eligible for narrowly scoped CI builds **only after** deployed-resource source binding and release policy verification. `integrations/hermes-paperclip/gateway/`, `integrations/*-overlay/`, `opik-run-enricher/` and `mcp-edge/` are explicit non-MCP or infrastructure exceptions: build only for a specifically approved active runtime, not on every repository push. Never classify by string matching alone when a manifest declares a special case.

For Coolify Git-backed source references used only for RepoWise bootstrap, disable automatic deployment; they are not application release targets. Do not delete them or their source code during repository cleanup.

## Production acceptance criteria

Reviewed commit SHA -> runner-built image digest -> immutable registry artifact -> image-only Coolify deployment -> verified runtime image digest, health/readback, rollback image retained. An image built directly by Coolify from Git **fails** this new local-build-only target even if it serves traffic.

No unrelated source-only path change may trigger an image build, nor can an MCP-only change rebuild non-MCP sources. Tests may still run without building images.

## Observed local-image canary (2026-11-09)

- Production `zar-i-szlif-web` (Coolify UUID `k0vwdsjazxguvgmh4qixjgxn`) still uses Dockerfile source mode. Git webhook auto-deploy was switched **off**; existing production remains on `98cd058155dbf4c268777246fc510324f98f7dc5`.
- Local Docker build of the approved commit from the Product RepoWise mirror completed; Dockerfile tests and runtime build passed.
- Private registry: Coolify project `local-build-image-registry`, Docker Image app `g0xdkztpmjnhgwms7qelzxqd`, persistent registry volume, listening **only** at `127.0.0.1:5000`. No public FQDN. Repository `127.0.0.1:5000/zar-i-szlif-web`.
- Immutable OCI manifest digest of the tested version: `sha256:478ab8d0fd10fbbb4f6162e05f41ae4d82f3e75745be10cacf48d6833847fdfe`. SHA-specific tag `98cd058155dbf4c268777246fc510324f98f7dc5`. Registry HEAD request returned matching digest.
- Image-only Coolify canary: project `zis-prebuilt-web-canary`, app `cs847jiwtuq5rlm8ntjeohgf`, no public FQDN. Successful deploy `jhhdy5nprjhpxrt5lzkxmbew` verified exact runtime release SHA and HTTP /healthz.
- **Failure injection:** setting the canary's runtime `SOURCE_COMMIT` to an invalid value caused the expected startup refusal and failed deploy `rbdqadkkkfl7fd1yrnbhjcum`. Coolify reported rollback, but the preserved container briefly returned **connection refused** despite a `healthy` health status. Therefore Docker's nominal health state is NOT sufficient rollback proof. After restoring the valid SHA, deploy `jpdf2phu5xc3hk0aocrlei1r` and HTTP readback passed.
- GHCR push was attempted and refused with `permission_denied`; the private loopback registry works instead.
- The installed Coolify GitHub App reports repository permission `administration:read` and **not** `administration:write`; GitHub requires Administration (write) to register repository self-hosted runners. Neither Product nor Harness repository has an online runner. No GitHub Actions runner E2E or automated production cutover is claimed.
- The native product promotion timer currently denies new main promotions with `non_merge_commit_on_main`. That issue is separate from image build delivery and must not be bypassed by promoting unreviewed commits.
- A disabled, nonpublic `image-mode-conversion-probe` application remains in Coolify pending manual deletion; native Coolify API rejected in-place change from Git-backed Dockerfile app to Docker Image mode. Production changeover therefore requires a staged image-app cutover, not an untested in-place build_pack mutation.

**Acceptance:** before cutover, require a registered runner or approved equivalent local scheduler, reviewed source and exact SHA, successful build and immutable image publication, an image-only production route with synchronized `SOURCE_COMMIT`, HTTP readback, and demonstrated rollback with real HTTP availability. Test-workspace success alone is not a production release.
