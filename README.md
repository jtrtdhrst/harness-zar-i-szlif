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

## Coolify monorepo build contract

**Source:** `miloszspyrka-code/harness-zar-i-szlif`, branch `main`.
Every MCP is built from its own root folder with its own Docker build context.
Do not point an MCP application at `zar-i-szlif` or the repo root.

| Service | Coolify base directory | Build pack / file | Watch paths |
| --- | --- | --- | --- |
| Paperclip MCP | `/paperclip-mcp` | Dockerfile `/Dockerfile` | `paperclip-mcp/**` |
| Plasmic MCP | `/plasmic-mcp` | Dockerfile `/Dockerfile` | `plasmic-mcp/**` |
| ComfyUI MCP | `/comfyui-mcp` | Dockerfile `/Dockerfile` | `comfyui-mcp/**` |
| Mantic MCP (HTTP) | `/mantic-mcp` | Dockerfile `/Dockerfile.http` | `mantic-mcp/**` |
| Qdrant MCP | `/qdrant-mcp` | Dockerfile `/Dockerfile` | `qdrant-mcp/**` |
| Supabase MCP | `/supabase-mcp` | Dockerfile `/Dockerfile` | `supabase-mcp/**` |
| Ubuntu MCP | `/ubuntu-mcp` | Dockerfile `/Dockerfile` | `ubuntu-mcp/**` |
| MCP edge (temporary) | `/mcp-edge` | Dockerfile `/Dockerfile.coolify` | `mcp-edge/**` |

Plasmic Studio (non-MCP) uses `/plasmic` and Docker Compose `/docker-compose.yml`.
The ComfyUI engine (non-MCP) is separately built from `comfyui-mcp/Dockerfile.comfyui`.

**Never deploy the bundled Qdrant MCP local Compose stack into an existing production Qdrant project:** it starts a separate database. Deploy the MCP Dockerfile only and configure `QDRANT_URL` for the existing Qdrant service. Ensure required runtime env/secrets, storage and health checks are validated before switching traffic.

Only enable path-based auto-deploy after the Coolify GitHub App can read this private repository and each app passes build + health + MCP tools/list. The migration-paused watch-path placeholder intentionally blocks auto-deploy until then.

This repository organization does not by itself validate or change live deployments, volumes, secrets, DNS, or routing.
