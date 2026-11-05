# Service catalog

This is a navigation index, not a second deployment inventory. The canonical project, service, volume and build-context map is [COOLIFY-PROJECTS.md](COOLIFY-PROJECTS.md); current per-resource promotion and evidence state is [`ops/release-lanes.json`](../ops/release-lanes.json) under [RELEASE-POLICY.md](RELEASE-POLICY.md). Both runtime status and the manifest's dated observations must be revalidated before release.

| Service/source area | Repository path | Notes |
| --- | --- | --- |
| Plasmic self-hosted application | `plasmic/` | Studio and WAB; build details are in the project map. |
| Plasmic MCP | `plasmic-mcp/` | Standalone MCP service. |
| Paperclip MCP | `paperclip-mcp/` | Owned MCP gateway/layer; Paperclip Core is upstream. |
| ComfyUI engine and historical combined source | `comfy/`, `comfyui-mcp/` | The combined directory is transitional/historical; see the project map. |
| ComfyUI MCP | `comfy-mcp/` | Standalone MCP service. |
| Mantic MCP | `mantic-mcp/` | Mautic integration MCP. |
| Emailens MCP | `emailens-mcp/` | Standalone bridge. |
| Playwright MCP | `playwright-mcp/` | Browser automation MCP. |
| Qdrant | `qdrant/` | Existing database/service source metadata. |
| Qdrant MCP | `qdrant-mcp/` | Connects to the existing Qdrant service; do not deploy a second database. |
| Supabase | `supabase/` | Existing platform/service source metadata. |
| Supabase MCP | `supabase-mcp/` | Standalone integration MCP. |
| Ubuntu MCP | `ubuntu-mcp/` | Host integration service. |
| MCP edge | `mcp-edge/` | Existing transitional edge service; retirement requires verified runtime evidence. |
| Hermes ↔ Paperclip integration | `integrations/hermes-paperclip/` | Gateway, adapter documentation, tests and evidence; the operations runbook is canonical. |
| Operations and release metadata | `ops/`, `docs/` | Policy, release-lane inventory and service/runbook navigation; not an application service. |

## Ownership

Infrastructure services, general-purpose MCPs and server integrations in this repository are owned by `miloszspyrka-code/harness-zar-i-szlif`. Product application, product website and product-only MCP source belong to `miloszspyrka-code/zar-i-szlif`. The root README is authoritative for that boundary. Do not infer deployment status from this catalog.
