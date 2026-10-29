# Harness — one service per folder

One-way source import from `miloszspyrka-code/zar-i-szlif` at `main` @ `e3dd9cbb419a39aa6934546a1aa9a310058d6573`.

| Service folder | Original product path |
|---|---|
| `paperclip-mcp/` | `mcp/paperclip/` |
| `plasmic-mcp/` | `mcp/plasmic/` |
| `plasmic/` | `plasmic/` (pinned upstream + local overlays) |
| `comfyui-mcp/` | `mcp/comfyui/` |
| `mantic-mcp/` | `mcp/mantic/` |
| `qdrant-mcp/` | `mcp/qdrant/` |
| `supabase-mcp/` | `mcp/supabase/` |
| `ubuntu-mcp/` | `mcp/ubuntu/` |
| `mcp-edge/` | `mcp/worker-edge/` |

Only source was copied; source repo was not changed. Existing Coolify, Cloudflare, service URLs, persistent volumes and secrets were not moved. Service docs and CI may still reference the old source paths; do not switch production or claim E2E without adjusting and validating them.

Plasmic's complete vendored snapshot can be regenerated using `plasmic/bootstrap-source.sh` (see `plasmic/MIGRATION-STATUS.md`).

## Branch recovery

Read [BRANCH-RECOVERY-20261029.md](BRANCH-RECOVERY-20261029.md). Historic fixes remain isolated from active code until reviewed and tested. Product and website changes belong in `kompaszbiorek-archiwum`, not here.

## Full migration of historical infrastructure and tooling — 2026-10-29

The non-product code from the former `zar-i-szlif` main is preserved here in `dev/`, `ops/`, `docs/`, `skills/`, `.paperclip-wiki/`, `scripts/`, `tests/`, `.githooks/` and `historical-root/`. Former `.github/` workflows were moved under `historical-actions/.github/` so they **cannot execute**. This snapshot also includes some legacy design-system reference files; it is an archive, not a production runtime. The complete item-by-item SHA inventory is in [`HISTORICAL-IMPORT-20261029.json`](HISTORICAL-IMPORT-20261029.json).

Do not activate old integrations, auto-deploy, cron, or workflows from this copied material without tests and production readback.
