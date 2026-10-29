# Harness — active services only

This repository is reserved for maintained application and MCP service source. Every active service owns a root folder.

## Service folders

- `plasmic/` — Plasmic self-hosted application
- `plasmic-mcp/` — Plasmic MCP
- `paperclip-mcp/` — Paperclip MCP
- `comfyui-mcp/` — ComfyUI MCP
- `mantic-mcp/` — Mantic MCP
- `qdrant-mcp/` — Qdrant MCP
- `supabase-mcp/` — Supabase MCP
- `ubuntu-mcp/` — Ubuntu MCP
- `mcp-edge/` — Edge gateway service (retain until deployment retirement is verified)

Historical files were transferred to `miloszspyrka-code/kompaszbiorek-archiwum` under `harness-legacy-20261029/`, preserving each file's relative path. Verified archived source SHA matches were removed from this repository.

**Outstanding cleanup:** Two binary PNGs remain under `dev/design-system/` because the GitHub connector does not allow their bytes to be read and copied. Do not delete them without a verified archive copy:
- `dev/design-system/6.png`
- `dev/design-system/strona-glowna-cloudflare/assets/logo.png`

This repository organization does not by itself validate or change live deployments, volumes, secrets, DNS, or routing.
