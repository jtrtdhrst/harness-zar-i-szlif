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
