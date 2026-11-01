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
