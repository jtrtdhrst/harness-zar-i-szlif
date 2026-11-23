> **Mapowanie kodu MCP na Coolify:** zobacz [ops/coolify-service-registry.json](../ops/coolify-service-registry.json). Poniższe informacje o wolumenach i wdrożeniach mają charakter historyczny; katalogi oficjalnych obrazów zostały wycofane z repo, ale zasoby Coolify pozostały.

# Coolify project / service / volume map

**Uwaga na zmiany katalogów:** Coolify produkcyjnie wskazuje jeszcze `/github-mcp` i `/multica-mcp` (odczyt 2026-11-23), a kanoniczne źródła tego PR to `mcp/github-mcp/` oraz `mcp/multica-mcp/`. Przed kolejnym deploy należy zsynchronizować `base_directory` i `watch_paths` w autoryzowanej procedurze release. Zielony CI PR nie dowodzi zgodności tych ustawień.

Source of truth for the Git layout. Service code is grouped by project; every project's runtime data must be attached to a resource in that
same project.

## Rules

1. One Coolify project owns exactly one main service named after the project
   (MCP projects: one `*-mcp` service).
2. All persistent data used by a service lives in a volume owned by that
   project and mounted by that service. No service mounts another project's
   volume.
3. `volumes/` in each folder contains only `.gitkeep` and documentation. Runtime
   data, dumps, model files, browser profiles and credentials are never committed.
4. Each source folder must be buildable from its own directory; no build may use the
   repository root as context.
5. `mcp/comfy-mcp/` contains only the MCP source. ComfyUI engine is a separate production service using its own runtime image and persistent volumes.

## Projects and data

| Coolify project | Service | Runtime data owned by the project | Git folder |
|---|---|---|---|
| `mautic` | `mautic` (+ `mantic-mcp`) | `*_mautic-prod-db`, `-config`, `-logs`, `-media*` | upstream Mautic image; `mcp/mantic-mcp/` for MCP |
| `supabase` | `supabase` | `*_supabase-staging-db-data`, storage, deno cache, SQL seed volumes | upstream Supabase images, not owned source |
| `paperclip` | `paperclip` | `*_paperclip-db`, `*_paperclip-home` | source removed from this repo; runtime not changed |
| `Plasmic` | `plasmic` | `*_plasmic-pgdata` | `apps/plasmic/` |
| `comfy` | `comfy` | `comfy_comfy-models`, `-input`, `-output`, `-user`, `-custom` | external/local ComfyUI engine image; `mcp/comfy-mcp/` is a different service |
| `opik` | `opik` | `*_opik-staging-clickhouse-*`, `-mysql`, `-minio-data`, `-redis-data`, `-zookeeper` | upstream Opik images, no owned source |
| `opik-mcp` | `opik-mcp` | backend, proxy and guard (talk to `opik`) | `mcp/opik-mcp/` |
| `paperclip-mcp` | `paperclip-mcp` | `*_paperclip-mcp-state` + project-owned `paperclip-mcp-legacy`; no cross-project bind | source removed from this repo; runtime not changed |
| `plasmic-mcp` | `plasmic-mcp` | `plasmic_mcp_state` | `mcp/plasmic-mcp/` |
| `supabase-mcp` | `supabase-mcp` | stateless (talks to `supabase`) | `mcp/supabase-mcp/` |
| `comfy-mcp` | `comfy-mcp` | stateless (talks to `comfy`) | `mcp/comfy-mcp/` |
| `coolify-mcp` | `coolify-mcp` | `*_coolify-mcp-oauth` state volume | `mcp/coolify-mcp/` |
| `github-ops-mcp` (BGH) | `github-ops-mcp` | stateless, root-owned rotated GitHub App credentials mounted read-only | `mcp/github-mcp/` |
| `emailens-mcp` | `emailens-mcp` | stateless | `mcp/emailens-mcp/` |
| `ubuntu-mcp` | `ubuntu-mcp` | `ubuntu-mcp-audit` | `mcp/ubuntu-mcp/` |
| `Multica MCP Control Plane` | `multica-mcp` | stateless (talks to `multica`) | `mcp/multica-mcp/` |
| `multica` | `multica-stack` | `backend-uploads`, `pgdata` | runtime images from upstream; `mcp/multica-mcp/` is a separate bridge |
| `Cloudflare Ingress i Edge` | `cloudflared-mcp`, edge | no application data; tunnel token is a mounted secret | Cloudflare runtime image; `gateways/mcp-edge/` for owned edge source |
| `shared-ingress` | `opencode`, proxy adapters | host bind paths, no Docker data volumes | local/external runtime image; source not attested |
| `Kod Aplikacji` | `kod-aplikacji` (panel) | panel-owned only | source inventory removed from this repo |
| `Kod MCP` | `playwright-mcp` + dev | browser state ephemeral | `mcp/playwright-mcp/` (the old `kod-mcp/` inventory was removed) |
| `Hermes Gateway POC` | — | disposable, archive | `_archive/hermes-gateway-poc/` |
| `Staging techniczny i testy` | — | empty after migration, delete | `_archive/staging-techniczny-i-testy/` |

## Build contract

| Folder | Build command | Dockerfile |
|---|---|---|
| `mcp/emailens-mcp/` | `docker build -t local/emailens-mcp:dev mcp/emailens-mcp/` | `mcp/emailens-mcp/Dockerfile` |
| `mcp/playwright-mcp/` | `docker build -t local/playwright-mcp:dev mcp/playwright-mcp/` | `mcp/playwright-mcp/Dockerfile` |
| `mcp/mantic-mcp/` | `docker build -f mcp/mantic-mcp/Dockerfile.http -t local/mantic-mcp:dev mcp/mantic-mcp/` | `mcp/mantic-mcp/Dockerfile.http` |
| `plasmic` | `docker compose -f apps/plasmic/docker-compose.yml build` | `studio.Dockerfile`, `platform/wab/Dockerfile` |
| `mcp/plasmic-mcp/` | `docker build -t local/plasmic-mcp:dev mcp/plasmic-mcp/` | `mcp/plasmic-mcp/Dockerfile` |
| `mcp/comfy-mcp/` | `docker build -t local/comfy-mcp:dev mcp/comfy-mcp/` | `mcp/comfy-mcp/Dockerfile` |
| `mcp/supabase-mcp/` | `docker build -t local/supabase-mcp:dev mcp/supabase-mcp/` | `mcp/supabase-mcp/Dockerfile` |
| `mcp/ubuntu-mcp/` | `docker build -t local/ubuntu-mcp:dev mcp/ubuntu-mcp/` | `mcp/ubuntu-mcp/Dockerfile` |
| `mcp/multica-mcp/` | `docker build -t local/multica-mcp:dev mcp/multica-mcp/` | `mcp/multica-mcp/Dockerfile` |
| `mcp/github-mcp/` (BGH) | `docker build --target verify -t local/github-mcp:verify mcp/github-mcp/ && docker build -t local/github-mcp:dev mcp/github-mcp/` | `mcp/github-mcp/Dockerfile` |
| `gateways/mcp-edge/` | `docker build -f gateways/mcp-edge/Dockerfile.coolify -t local/mcp-edge:dev gateways/mcp-edge/` | `gateways/mcp-edge/Dockerfile.coolify` |

## Migration notes (current canonical layout)

- `mcp/comfy-mcp/` is **active canonical MCP source**, not an obsolete combined folder. The separate `comfy` service runs its existing local/upstream image and stores models and outputs in its own persistent volumes.
- Bridges `emailens-mcp`, `mantic-mcp`, and `ubuntu-mcp` have independent code under `mcp/`; their providers or engine stacks are separate resources.
- Mautic, Supabase, Opik Core, ComfyUI Engine and Qdrant DB are runtime resources; do not invent local owner-source folders for vendor or unknown-source images.
- `mcp/opik-mcp/` and `workers/opik-run-enricher/` are separate components, whereas `ops/` contains shared deployment metadata, not an Opik process.

`mcp/qdrant-mcp/` is the canonical source of the running Qdrant MCP service. Qdrant database is a separate upstream runtime; removing historical `qdrant/` metadata does not delete its deployed collections or volumes. Any retirement of live resources requires separate inventory and migration.

The retired root inventories `kod-aplikacji/` and `kod-mcp/` do not own current production MCP source. The Coolify inventory above describes **runtime resources only**, not their ownership by this repository. Removing Git paths does not delete services, images, databases, Docker volumes or secrets.
