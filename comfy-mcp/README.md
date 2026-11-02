# comfy-mcp

Coolify project/service folder. Runtime data volumes are owned by this
project; only `volumes/` markers are committed.

- Project metadata: `project.yml`
- Runtime source/image: see `docs/COOLIFY-PROJECTS.md`
- No secrets or runtime data in Git.

## ChatGPT image attachment bridge (2026-11-01)

- Source: `chatgpt-file-tool.js`; Docker build definition: `Dockerfile.chatgpt-files`.
- Production Coolify service: `kkhfw0napmeaqewgdirwhc1h`; current image: `local/comfyui-mcp:0.52.206-chatfiles4`.
- Origin: `http://comfy-mcp:9100/mcp` on the shared `coolify` Docker network; Cloudflare hostname: `https://mcp-comfy.kompaszbiorek.pl/mcp`.
- ChatGPT-specific tool: `upload_chatgpt_image`, declares `_meta["openai/fileParams"]=["file"]`, accepts an OpenAIFile with required `download_url` and `file_id`, optional `file_name` and `mime_type`.
- Safeguards: HTTPS only, public DNS IP pinning, no URL redirects, 30 MiB limit, valid image signature/extension, SHA-256 output, temporary-file cleanup, LoadImage validation, and respects `COMFYUI_MCP_TOOL_PRESET=readonly`.
- Existing `upload_image` remains unchanged.
- Build from a clone of the repository on the Coolify Docker host:
  `docker build --pull=false -f comfy-mcp/Dockerfile.chatgpt-files -t local/comfyui-mcp:0.52.206-chatfiles4 comfy-mcp`.
- The protected public endpoint uses `COMFYUI_MCP_HTTP_TOKEN` stored as a Coolify service environment variable. Do NOT commit the value or disable the origin authorization.
- **ChatGPT integration gate:** ChatGPT's custom-MCP connection does not supply arbitrary static API keys; existing no-auth ChatGPT connections now receive 401. The service is ready, but attachment delivery directly from ChatGPT needs a compatible OAuth 2.1 or Secure MCP Tunnel connection, then a tool rescan. Do not call this ChatGPT-side E2E complete without that.
- Verified production HTTPS MCP initialize + tools/list (42 tools, correct `fileParams` metadata), authenticated upload of a public test PNG + input-volume SHA-256 and `LoadImage` selectable. Rejected local/private/insecure URLs and confirmed readonly tool suppression in a canary.


## Lossless ChatGPT attachment delivery (2026-11-02)

- Production Coolify app image: `local/comfyui-mcp:0.52.206-chatfiles5` (same service, no ComfyUI/Core edits).
- `upload_chatgpt_image` keeps original attachment bytes: HTTPS download, no resize/transcode, secure temp file, native ComfyUI upload, LoadImage enumeration, and independent GET `/view?type=input&filename=...` SHA-256/byte-count readback. A mismatch FAILS the tool.
- Optional `expected_sha256` and `expected_bytes` prevent use of a truncated/altered source. On success, structured output includes `byte_identical:true`, `sha256`, `readback_sha256`, `stored_bytes`, and `loader_selectable:true`.
- Authenticated MCP gateway: `https://mcp-comfy-chat.zariszlif.pl/mcp`. Cloudflare Access Managed OAuth (owner-email policy, DCR with both stable and callback-specific ChatGPT redirect URIs) forwards to `comfy-mcp-access-bridge:9101`. Bridge checks Access RS256 signature against Cloudflare JWKS, issuer, audience, expiry, and principal, then forwards to the internal MCP with the **existing** origin token (inherited from Coolify's local env file; no secret in the repository). Source: `oauth-bridge.mjs`, compose reference: `oauth-bridge.compose.yml`.
- Host-managed bridge location: `/opt/comfy-mcp-access-bridge/`, restart policy `unless-stopped`, health check; production ComfyUI MCP remains separately managed by Coolify.
- Verified: signed JWT fixture → MCP initialize → tools/list (42 tools including `_meta["openai/fileParams"]`) → `upload_chatgpt_image` → independent ComfyUI byte readback. Bad signature, expired JWT, and incorrect SHA were rejected. Production `upload_image` also preserved a 1254×1254 RGBA PNG with exact SHA-256.
- **Outstanding user-authenticated acceptance:** a previously installed ChatGPT ComfyUI connector pointing to the older token-only endpoint will still produce UNAUTHORIZED. Reconnect it to the new Cloudflare OAuth endpoint and rescan; user must complete Cloudflare Access login. Then submit an actual ChatGPT attachment and compare its known original SHA-256 to `readback_sha256`. Do not label that last step DONE until observed.
