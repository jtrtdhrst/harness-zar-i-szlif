# Repository architecture

This repository is the source home for infrastructure services and standalone integration MCPs. It is separate from the Żar i Szlif product repository; repository and path ownership are summarized in the root [README](../README.md).

## Source layout

Each active infrastructure service has a service-owned root directory and build context. The service and project mapping, data/volume ownership, and build commands are maintained in [COOLIFY-PROJECTS.md](COOLIFY-PROJECTS.md). Product folders and metadata-only Coolify project inventories are not alternate source locations.

| Concern | Canonical location |
| --- | --- |
| Infrastructure MCPs and integrations | Service roots listed in [SERVICE-CATALOG.md](SERVICE-CATALOG.md) |
| Hermes ↔ Paperclip adapter, gateway and operations evidence | [`integrations/hermes-paperclip/`](../integrations/hermes-paperclip/README.md); see its [operations status](../integrations/hermes-paperclip/OPERATIONS-STATUS.md) |
| Paperclip MCP gateway and its owned MCP layer | [`paperclip-mcp/`](../paperclip-mcp/README.md); Paperclip Core remains upstream and is not vendored here |
| Project/service/volume mapping and build contexts | [COOLIFY-PROJECTS.md](COOLIFY-PROJECTS.md) |
| Per-service release provenance, approval and rollback | [RELEASE-POLICY.md](RELEASE-POLICY.md) and [`ops/release-lanes.json`](../ops/release-lanes.json) |

## Runtime boundaries

A directory or Dockerfile describes candidate source layout; it does not prove which image or source revision is running. Runtime data, credentials, and persistent volumes remain in their existing service/project boundaries. Release evidence must tie the reviewed source SHA to an immutable artifact and current runtime readback under the relevant service lane.

The release manifest is a dated inventory, not a live discovery mechanism. Some entries are explicitly held or lack source-to-digest proof. Follow the release policy and obtain current, authenticated service evidence before any deployment decision.

## Repository-context admission

For each issue/run, follow the managed `agent-git-delivery` skill and canonical Wiki policy. Record exact document hashes and workspace ownership in the existing issue checkpoint before mutation. This documents auditable behavior; it does not itself provide server-side write enforcement or prove that a document was read.
