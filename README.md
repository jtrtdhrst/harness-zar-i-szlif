# Harness — one service per folder

One-way source import from `miloszspyrka-code/zar-i-szlif` at `main` @ `e3dd9cbb419a39aa6934546a1aa9a310058d6573`.

| Service folder | Original product path |
|---|---|
| `paperclip-mcp/` | `mcp/paperclip/` |
| `plasmic-mcp/` | `mcp/plasmic/` |
| `plasmic/` | `plasmic/` (pinned upstream + local overlays) |
| `comfyui-mcp/` | `mcp/comfyui/` |
| `langfuse-mcp/` | `mcp/langfuse/` |
| `mantic-mcp/` | `mcp/mantic/` |
| `qdrant-mcp/` | `mcp/qdrant/` |
| `supabase-mcp/` | `mcp/supabase/` |
| `ubuntu-mcp/` | `mcp/ubuntu/` |
| `mcp-edge/` | `mcp/worker-edge/` |
| `opencode-mcp/` | `dev/integrations/opencode-mcp/` (upstream submodule kept) |
| `paperclip-local-mcp/` | `dev/integrations/paperclip-mcp/` |

Only source was copied; source repo was not changed. Existing Coolify, Cloudflare, service URLs, persistent volumes and secrets were not moved. Service docs and CI may still reference the old source paths; do not switch production or claim E2E without adjusting and validating them.

Plasmic's complete vendored snapshot can be regenerated using `plasmic/bootstrap-source.sh` (see `plasmic/MIGRATION-STATUS.md`).
