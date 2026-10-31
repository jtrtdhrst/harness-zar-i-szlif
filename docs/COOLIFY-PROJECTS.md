# Coolify project / service / volume map

Source of truth for the Git layout. Every active service has its own root
folder; every project's runtime data must be attached to a resource in that
same project.

## Rules

1. One Coolify project owns exactly one main service named after the project
   (MCP projects: one `*-mcp` service).
2. All persistent data used by a service lives in a volume owned by that
   project and mounted by that service. No service mounts another project's
   volume.
3. `volumes/` in each folder contains only `.gitkeep` and documentation. Runtime
   data, dumps, model files, browser profiles and credentials are never committed.
4. Each folder must be buildable from its own directory; no build may use the
   repository root as context.
5. `comfyui-mcp/` is the temporary combined ComfyUI build folder; the target
   split is `comfy/` (engine) and `comfy-mcp/` (MCP). Do not add a second
   Qdrant database to `qdrant-mcp/`.

## Projects and data

| Coolify project | Service | Runtime data owned by the project | Git folder |
|---|---|---|---|
| `mautic` | `mautic` (+ `mantic-mcp`) | `*_mautic-prod-db`, `-config`, `-logs`, `-media*` | `mautic/` |
| `supabase` | `supabase` | `*_supabase-staging-db-data`, storage, deno cache, SQL seed volumes | `supabase/` |
| `paperclip` | `paperclip` | `*_paperclip-db`, `*_paperclip-home` | `paperclip/` |
| `Plasmic` | `plasmic` | `*_plasmic-pgdata` | `plasmic/` |
| `qdrant` | `qdrant` | `*_qdrant-storage` | `qdrant/` |
| `comfy` | `comfy` | `comfy_comfy-models`, `-input`, `-output`, `-user`, `-custom` | `comfyui-mcp/` (until split) |
| `opik` | `opik` | `*_opik-staging-clickhouse-*`, `-mysql`, `-minio-data`, `-redis-data`, `-zookeeper` | `opik/` (planned) |
| `opik-mcp` | `opik-mcp` | stateless (talks to `opik`) | `opik-mcp/` (planned) |
| `paperclip-mcp` | `paperclip-mcp` | `*_paperclip-mcp-state` + project-owned `paperclip-mcp-legacy`; no cross-project bind | `paperclip-mcp/` |
| `plasmic-mcp` | `plasmic-mcp` | `plasmic_mcp_state` | `plasmic-mcp/` |
| `qdrant-mcp` | `qdrant-mcp` | stateless (talks to `qdrant`) | `qdrant-mcp/` |
| `supabase-mcp` | `supabase-mcp` | stateless (talks to `supabase`) | `supabase-mcp/` |
| `comfy-mcp` | `comfy-mcp` | stateless (talks to `comfy`) | `comfy-mcp/` |
| `coolify-mcp` | `coolify-mcp` | `*_coolify-mcp-oauth` state volume | `coolify-mcp/` (planned) |
| `emailens-mcp` | `emailens-mcp` | stateless | `emailens-mcp/` |
| `ubuntu-mcp` | `ubuntu-mcp` | `ubuntu-mcp-audit` | `ubuntu-mcp/` |
| `Cloudflare Ingress i Edge` | `cloudflared-paperclip`, edge | no application data; tunnel token is a mounted secret | `cloudflare-ingress/` (planned) |
| `shared-ingress` | `opencode`, `oauth-callback-proxy`, `oauth-loopback-bridge` | host bind paths, no Docker data volumes | `shared-ingress/` |
| `Kod Aplikacji` | `kod-aplikacji` (panel) | panel-owned only | `kod-aplikacji/` (planned) |
| `Kod MCP` | `playwright-mcp` + dev | browser state ephemeral | `playwright-mcp/` |
| `Hermes Gateway POC` | — | disposable, archive | `_archive/hermes-gateway-poc/` |
| `Staging techniczny i testy` | — | empty after migration, delete | `_archive/staging-techniczny-i-testy/` |

## Build contract

| Folder | Build command | Dockerfile |
|---|---|---|
| `emailens-mcp` | `docker build -t local/emailens-mcp:0.10.0 emailens-mcp` | `emailens-mcp/Dockerfile` |
| `playwright-mcp` | `docker build -t local/playwright-mcp:0.0.83 playwright-mcp` | `playwright-mcp/Dockerfile` |
| `mantic-mcp` | `docker build -f mantic-mcp/Dockerfile.http mantic-mcp` | `Dockerfile.http` |
| `paperclip-mcp` | `docker build -t local/paperclip-mcp paperclip-mcp` | `Dockerfile` |
| `plasmic` | `docker compose -f plasmic/docker-compose.yml build` | `studio.Dockerfile`, `platform/wab/Dockerfile` |
| `plasmic-mcp` | `docker build -t local/plasmic-mcp plasmic-mcp` | `Dockerfile` |
| `comfyui-mcp` | `docker build -f comfyui-mcp/Dockerfile.comfyui comfyui-mcp` / `-f Dockerfile` | engine / MCP |
| `qdrant-mcp` | `docker build -t local/qdrant-mcp qdrant-mcp` | `Dockerfile` |
| `supabase-mcp` | `docker build -t local/supabase-mcp supabase-mcp` | `Dockerfile` |
| `ubuntu-mcp` | `docker build -t local/ubuntu-mcp ubuntu-mcp` | `Dockerfile` |
| `mcp-edge` | `docker build -f mcp-edge/Dockerfile.coolify mcp-edge` | `Dockerfile.coolify` |

## Pending structural cleanup

These are tracked as migration work, not silently ignored:

- ComfyUI is now split into `comfy` and `comfy-mcp`; the old combined
  `comfyui-mcp/` folder remains only as historical build source.
- `mcp-bridges` is split into `emailens-mcp`, `mantic-mcp` (in `mautic`) and
  `ubuntu-mcp`; old app containers removed.
- platform folders (`mautic`, `supabase`, `paperclip`, `qdrant`, `opik`,
  `comfy`) are metadata/build-contract folders; their upstream images/source
  remain external.
