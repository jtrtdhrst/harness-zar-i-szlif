# Harness — active services only

This repository owns **infrastructure services and standalone integration MCPs**, not the Żar i Szlif product application or its own product MCP. Every active infrastructure service owns a root folder.

**Repository boundary (2026-11-02):** code for the Żar i Szlif product, product websites and **only its application-specific MCP** belongs in [`miloszspyrka-code/zar-i-szlif`](https://github.com/miloszspyrka-code/zar-i-szlif), under `product/`, `www/` and `mcp/` respectively. General-purpose MCP servers, VPS integrations and Hermes Gateway integration belong here. Do not recreate `zar-i-szlif/mcp-bridges/`: its obsolete copies were deleted from the product `main` in PR #139 and are recoverable from Git history. The metadata folders `kod-aplikacji/` and `kod-mcp/` are Coolify project inventories only, **not** alternate product-code locations. The Hermes Gateway receiver and adapter are under review in [PR #36](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/36), with execution evidence and release gates tracked in the [Hermes E2E runbook](integrations/hermes-paperclip/OPERATIONS-STATUS.md). The historical source-binding PR #6 was closed without merge. Source security review of H01 alone does not constitute approval of H02/H05 or production cutover; require a real Paperclip-issued, issue-scoped authenticated E2E run before promotion.

## Service folders

- `plasmic/` — Plasmic self-hosted application
- `plasmic-mcp/` — Plasmic MCP
- `paperclip-mcp/` — Paperclip MCP
- `integrations/hermes-paperclip/` — source-pinned Hermes Gateway receiver, Paperclip adapter and [runbook](integrations/hermes-paperclip/OPERATIONS-STATUS.md)
- `comfyui-mcp/` — ComfyUI engine + MCP (independently versioned image builds; verify each active deployment)
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

## Source ownership and candidate build layout — not a production deployment claim

**Source owner:** `miloszspyrka-code/harness-zar-i-szlif`. `main` is an integration branch, **not** a universal production release ref. Existing infrastructure MCP services include image-only/upstream-pinned Coolify resources. A folder, Dockerfile or green GitHub Action alone does not prove automatic deployment. Promote an exact reviewed image/ref per service only after its own Git-backed canary, health, authenticated MCP test, immutable digest, runtime readback and rollback. Current per-service policies and observed baselines are tracked in [release-lane PR #41](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/41); review/merge and live acceptance remain separate.

The **unified Paperclip Core + Hermes adapter candidate** deliberately uses the repository-root build context to apply pinned Core review-recovery and Hermes adapter overlays together. This special case does not imply a general rule to deploy other infrastructure MCPs from the repo root. Only a reviewed, tested source SHA may be promoted; the 14-agent migration remains gated by real Wiki/Skills, Hindsight, Opik and rollback validation.

The table below is a **candidate source layout** for independently verified service bindings, not an assertion that every production resource already builds from Git. Do not point general-purpose infrastructure MCPs to `zar-i-szlif` or the repo root. The **product MCP** belongs exclusively in the separate product repository.

| Service | Candidate build directory | Dockerfile / build source | Watch paths after verified Git binding |
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
