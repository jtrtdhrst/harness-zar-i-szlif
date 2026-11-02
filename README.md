# Harness — active services only

This repository owns **infrastructure services and standalone integration MCPs**, not the Żar i Szlif product application or its own product MCP. Every active infrastructure service owns a root folder.

**Repository boundary (2026-11-02):** code for the Żar i Szlif product, product websites and **only its application-specific MCP** belongs in [`miloszspyrka-code/zar-i-szlif`](https://github.com/miloszspyrka-code/zar-i-szlif), under `product/`, `www/` and `mcp/` respectively. General-purpose MCP servers, VPS integrations and Hermes Gateway integration belong here. Do not recreate `zar-i-szlif/mcp-bridges/`: its obsolete copies were deleted from the product `main` in PR #139 and are recoverable from Git history. The metadata folders `kod-aplikacji/` and `kod-mcp/` are Coolify project inventories only, **not** alternate product-code locations. The Hermes Gateway Dockerfile exists in open infrastructure PR #6 pending review, and has been build-tested in Coolify; do not claim that it is already merged into `main` or active as the production runtime.

## Service folders

- `plasmic/` — Plasmic self-hosted application
- `plasmic-mcp/` — Plasmic MCP
- `paperclip-mcp/` — Paperclip MCP
- `comfyui-mcp/` — ComfyUI engine + MCP (split pending)
- `mantic-mcp/` — Mantic MCP
- `emailens-mcp/` — Emailens MCP bridge
- `playwright-mcp/` — Playwright MCP with idle HTTP proxy
- `qdrant-mcp/` — Qdrant MCP
- `supabase-mcp/` — Supabase MCP
- `ubuntu-mcp/` — Ubuntu MCP
- `mcp-edge/` — Edge gateway service (retain until deployment retirement is verified)

Project folders without vendored source are metadata-only; their runtime
source/image is recorded in `docs/COOLIFY-PROJECTS.md`. Each service folder
owns its `volumes/` directory. Runtime data stays in the
same Coolify project; only `.gitkeep` and documentation are committed. See
[`docs/COOLIFY-PROJECTS.md`](docs/COOLIFY-PROJECTS.md) for the project/service/
volume map and pending structural cleanup.

Historical files were transferred to `miloszspyrka-code/kompaszbiorek-archiwum` under `harness-legacy-20261029/`, preserving each file's relative path. Verified archived source SHA matches were removed from this repository.

## Coolify monorepo build contract

**Source:** `miloszspyrka-code/harness-zar-i-szlif`, branch `main`.
Every **infrastructure MCP in this repository** is built from its own root folder with its own Docker build context. Do not point these infrastructure deployments at `zar-i-szlif` or the repo root. The **product MCP** is the sole MCP exception and belongs in the separate product repository.

| Service | Coolify base directory | Build pack / file | Watch paths |
| --- | --- | --- | --- |
| Paperclip MCP | `/paperclip-mcp` | Dockerfile `/Dockerfile` | `paperclip-mcp/**` |
| Plasmic MCP | `/plasmic-mcp` | Dockerfile `/Dockerfile` | `plasmic-mcp/**` |
| ComfyUI MCP | `/comfyui-mcp` | Dockerfile `/Dockerfile` | `comfyui-mcp/**` |
| Mantic MCP (HTTP) | `/mantic-mcp` | Dockerfile `/Dockerfile.http` | `mantic-mcp/**` |
| Emailens MCP | `/emailens-mcp` | Dockerfile `/Dockerfile` | `emailens-mcp/**` |
| Playwright MCP | `/playwright-mcp` | Dockerfile `/Dockerfile` | `playwright-mcp/**` |
| Qdrant MCP | `/qdrant-mcp` | Dockerfile `/Dockerfile` | `qdrant-mcp/**` |
| Supabase MCP | `/supabase-mcp` | Dockerfile `/Dockerfile` | `supabase-mcp/**` |
| Ubuntu MCP | `/ubuntu-mcp` | Dockerfile `/Dockerfile` | `ubuntu-mcp/**` |
| MCP edge (temporary) | `/mcp-edge` | Dockerfile `/Dockerfile.coolify` | `mcp-edge/**` |

Plasmic Studio (non-MCP) uses `/plasmic` and Docker Compose `/docker-compose.yml`.
The ComfyUI engine (non-MCP) is separately built from `comfyui-mcp/Dockerfile.comfyui`.

**Never deploy the bundled Qdrant MCP local Compose stack into an existing production Qdrant project:** it starts a separate database. Deploy the MCP Dockerfile only and configure `QDRANT_URL` for the existing Qdrant service. Ensure required runtime env/secrets, storage and health checks are validated before switching traffic.

The Coolify GitHub App can now read this private repository (verified 2026-11-02). Enable per-service path-based auto-deploy only after each app passes build + health + MCP tools/list and authorized tools/call tests. The migration-paused watch-path placeholder intentionally blocks auto-deploy until then.

This repository organization does not by itself validate or change live deployments, volumes, secrets, DNS, or routing.
