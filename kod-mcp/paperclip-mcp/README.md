# Paperclip MCP

MCP layer of the Paperclip control plane: the Streamable HTTP gateway that exposes
the Paperclip MCP server (tools, issues, agents, projects, workspaces) to Paperclip
itself, to Claude Web custom connectors (OAuth 2.1), and to any MCP client.

```
client ──Bearer / OAuth──▶ gateway.mjs :3101/mcp ──▶ /paperclip/mcp-patch/src/* ──▶ Paperclip API :3100
```

| Path | What it is |
|---|---|
| `mcp-gateway/gateway.mjs` | HTTP + OAuth gateway (JSON-RPC → Paperclip MCP server) |
| `mcp-gateway/principal.mjs` | principal resolution (agent / board key) |
| `src/` | the MCP server sources (`index.ts`, `tools.ts`, `execution-broker.ts`, `host-ops.ts`, …) — the patched Paperclip MCP package |

**Paperclip core is not vendored.** The API/UI/scheduler/OAuth/migrations stay in the
upstream image `ghcr.io/paperclipai/paperclip`; only the MCP layer above is owned by
this folder (and it is the only part allowed to be patched).

## Build

```bash
# upstream Paperclip release as base
docker build -t paperclip-mcp-gateway:local .

# the deployed runtime as base (adds /app/paperclip-public-mcp/plugin-skills,
# which the gateway lists as MCP skills — without it the gateway aborts at boot)
docker build --build-arg PAPERCLIP_BASE=local/paperclip-opencode-runtime:1.18.32-mcpfix-20261013 \
  -t paperclip-mcp-gateway:local .
```

```bash
docker run --rm -p 3101:3101 \
  -e PAPERCLIP_API_URL=http://paperclip:3100/api \
  -e PAPERCLIP_COMPANY_ID=<company-uuid> \
  -e MCP_PUBLIC_BASE_URL=https://paperclip-mcp.example.pl \
  -v "$PWD/state:/paperclip" \
  paperclip-mcp-gateway:local
```

`/paperclip` must be a writable volume: the gateway persists `oauth-store.json`,
`url-tokens.json` and the OAuth client registry there. The image carries the code
in `/opt/paperclip-mcp` and materializes it into `/paperclip` on start (the volume
would otherwise shadow it).

`PAPERCLIP_COMPANY_ID` is mandatory — the gateway exits at boot without a valid UUID.

## Endpoints

- `POST /mcp` — MCP Streamable HTTP (Bearer `pcp_…` API key or OAuth access token).
- `GET /health` — gateway health.
- `GET /.well-known/oauth-authorization-server` — OAuth 2.1 metadata for custom connectors.

## Current Coolify production (2026-11-02)

The **actual running Paperclip MCP** is a Coolify **service** (`gevr1m6rdj4t4fbhcjvqv8gg`), with sub-application `yvtwulblrzpmuvi72xd9sey3`, internal port 3101 and existing `/paperclip` persistent volume. Its source belongs in this repository's **`kod-mcp/paperclip-mcp/`** folder; do not put gateway source into the product's `zar-i-szlif` repository or modify Paperclip Core.

The current production image is `paperclip-mcp:chatgpt-image-final-20261102` (digest `sha256:b5c9a29df706ac7cd5fde3cfe9ee68c9dc6dd793b57008e5593bc6cbf2d60762`). Previous working image tag for rollback: `fs9rik9axzl1ubbimekvqs03:eadd6814c29c23cd139958fa3705e197fc60b6c6`. Coolify uses local image `pull_policy: never`: **GitHub main changes do not auto-build or redeploy this service**. Any production release requires an explicit image build, named image switch through Coolify and post-deploy digest/MCP readback. Preserve OAuth and other data volumes. A future trusted GHCR publish/Git-based build could close this reproducibility gap, but do not invent it or move to another service.

Canonical production public endpoint: `https://paperclip-mcp.zariszlif.pl/mcp`; verify its authenticated `initialize`, `tools/list`, `tools/call`, OAuth discovery, denied anonymous calls, and running image digest. Health 200 alone is not proof. Cloudflare remains DNS/TLS/tunnel transport; retain the existing `paperclip-mcp` Worker and other unrelated Workers, routes and tunnel settings.

### ChatGPT image transfer

The existing gateway now exposes `paperclipUploadChatgptImage` with an official OpenAI `file` object, `_meta["openai/fileParams"]=["file"]`, persistent byte-exact upload, ComfyUI `LoadImage` staging, independent SHA-256 verification and a Paperclip issue receipt attempt. See **[docs/chatgpt-image-ingress.md](docs/chatgpt-image-ingress.md)** for schema, security policy, production test results and the remaining external ChatGPT connector validation.

Source patches are limited to `mcp-gateway/chatgpt-image.mjs`, `gateway.mjs`, `entrypoint.sh` and the MCP live registry `src/live-verify.ts`; no Paperclip Core edits, additional agents or new infrastructure.

## Production safety and release

Use source control, static validation, a canary where practical and existing Coolify service controls. Keep the previous exact image tag for rollback. The current production image is a minimal overlay on the prior deployed custom Paperclip MCP image, so **it is not independently reconstructible from the public base image alone**. Do not present a running container as proof of portable disaster recovery; preserve a trusted base image and automate image publishing separately after verification.

## Provenance

Extracted from the running containers `paperclip-mcp-gateway` /
`paperclip-mcp-gateway-pub` (image `local/paperclip-opencode-runtime:1.18.32-mcpfix-20261013`,
Paperclip build `v2026.1012.0-0-gbba6a45f0`).


