# Multica MCP control plane

Independent, stateless MCP adapter for the installed Multica **v0.8.1** CLI at commit `b1ea927def6490c43bedff537b6f4ed9a47fa828`. It does not patch or deploy Multica Core. The Dockerfile copies the pinned CLI from the public `ghcr.io/multica-ai/multica-backend:v0.8.1` image; each tool invocation delegates to it with the caller’s token, so Multica remains the authorization authority.

## Transports and identity

- Streamable HTTP: `POST /mcp`; liveness: unauthenticated `GET /health`.
- stdio: `node server.mjs stdio`, with `MULTICA_TOKEN` set by the MCP host.
- HTTP requires `Authorization: Bearer <Multica PAT or task-scoped mat_ token>` on every MCP request, or the same token as a `?key=` query parameter when the MCP client cannot set headers. Query tokens leak into proxy/access logs; prefer the header. The adapter never stores the token and never falls back to a profile, administrator PAT, cookie, or client-supplied identity header. Multica validates/revokes the token and enforces its real user/agent/task/workspace permissions.
- Supply `workspace_id` per tool call where needed. Multica performs the membership and role checks.
- OAuth is **not implemented**: the installed Multica version is not a generic OAuth authorization server. No OAuth token exchange is emulated. Use a caller-owned, revocable Multica PAT or the task’s actual `mat_` token.
- MCP request cancellation stops the local CLI process only; it does not claim to cancel an already accepted Multica run. Use the native `issue.cancel-task` tool for Multica run cancellation.

## Catalog and compatibility

At startup, the adapter discovers leaf commands and argument types from the pinned CLI’s own `--help` output. `tools/list` exposes every native, non-host-local operation as an individual fixed tool. It never accepts a command string, shell fragment, arbitrary URL, or arbitrary HTTP path. Unknown flags/arguments are rejected, subprocesses run with `shell:false`, and credentials are excluded from logs and redacted from returned output.

The complete machine-readable catalog is available as the MCP resource `multica://capabilities/v0.8.1.json` and can be regenerated with `npm run catalog` (requires the pinned CLI at `MULTICA_CLI`). It includes every discovered CLI leaf, typed flag schema, filtered host-local flags, and one status:

- `PASS_NATIVE`: fixed operation delegated to the pinned CLI with caller identity.
- `BLOCKED`: depends on a file/path in the CLI container that is not the caller’s filesystem.
- `ARCHITECTURALLY_INCOMPATIBLE`: local login/config/daemon/profile command that cannot safely operate as a remote Multica control-plane operation.
- `PASS_ADAPTER`: HTTP/stdio transport and JSON-RPC surface.
- `PASS_EXTERNAL_INTEGRATION`: none claimed.
- `FAIL`: none silently converted into success; runtime errors return MCP `isError: true`.

The read-only Paperclip snapshot in `docs/paperclip-tool-baseline.json` contains all 200 observed Paperclip tool names. Its parity matrix labels every direct Paperclip operation `ARCHITECTURALLY_INCOMPATIBLE`: this service is for Multica and never calls or modifies Paperclip. Conceptual similarities are not represented as semantic parity.

Destructive native commands require `confirm: true` in the MCP call in addition to Multica’s own permission checks. Host-local file/path flags are not exposed. The process is bounded to 120 seconds and 2 MiB of output.

## Build and test

Requires Node 24+ and Docker. The CLI is copied from the pinned public backend image, so no local binary is needed:

```sh
npm test
docker build -t local/multica-mcp-control-plane:0.2.0 .
```

The Docker image fails closed unless the copied CLI reports v0.8.1 and commit prefix `b1ea927de`. No npm packages or database are required. `npm run catalog` additionally requires `MULTICA_CLI` to point at that binary.

## Coolify deployment

Production is a Coolify Git-backed application from this folder (`base_directory=/multica-mcp`, `Dockerfile=/Dockerfile`, watch path `multica-mcp/**`). Coolify builds on every push to `main`; no local image or host build context is used. The dedicated Cloudflare Tunnel connector is a separate Coolify service and routes `mcp-multifca.zariszlif.pl` to `http://multica-mcp:3000` over the `coolify` network alias. Keep `TUNNEL_TOKEN` in Coolify’s secret environment variables, never in Git or Compose source.

The local `docker-compose.yml` is for development only. It publishes port 3000 and does not include the tunnel connector.

`MULTICA_API_URL` defaults to `https://multica.zariszlif.pl`; update it only when the native Multica endpoint is intentionally migrated. The MCP endpoint is `https://mcp-multifca.zariszlif.pl/mcp`.

## Upgrade and rollback

Keep the adapter in this repository and commit every release. To upgrade, pin the new CLI version/commit, update `catalog.mjs`, regenerate the catalog, run all tests, commit, and let Coolify rebuild the application. No Multica migration is performed. For rollback, revert the adapter commit and redeploy; do not reset shared state. Verify `/health`, MCP initialize/list/call, and a token-scoped read/write/readback before declaring completion.

## Known limits

- No generic OAuth server, OAuth discovery, or token broker exists in Multica v0.8.1; OAuth clients requiring that contract are blocked until Multica provides an authorization-server integration.
- Local daemon/config/login commands and CLI-host file transfers are not exposed as remote capabilities.
- The Paperclip 200-tool inventory is a read-only differential baseline, not a promise to implement Paperclip behavior in Multica.
- This adapter does not implement Core scheduling, queueing, workflow, permissions, PR completion, or task cancellation; these remain native Multica behavior.
