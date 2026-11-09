---
title: MCP Qdrant Hybrid — endpoint w sieci Paperclip
type: entity
tags: [mcp, qdrant, retrieval]
created: 2026-09-07
updated: 2026-10-04
---

# MCP Qdrant Hybrid — endpoint w sieci Paperclip

**Owner:** MCP Engineer (`wiki/agents/mcp-engineer/AGENTS.md`). This is a separate Python MCP service, not Paperclip application source and not the Kompas product repository.

Dense embeddings use FastEmbed `BAAI/bge-small-en-v1.5` (CPU); sparse retrieval uses FastEmbed BM25 (`Qdrant/bm25`). Domain data remains in its authoritative application stores.

## Current runtime

- MCP: `http://mcp-qdrant:8000/mcp` on `paperclip-net`; stateless streamable HTTP.
- Container/image: `mcp-qdrant`, `mcp-qdrant-hybrid:latest`; restart policy `unless-stopped`; no host-published port or bind mounts.
- Backend: Qdrant Cloud; collection `long_term_memory`.
- Vectors: `text-dense` 384/Cosine and `text-sparse` with `Modifier.IDF`.
- Runtime credentials stay in the host container environment. Do not copy them into the project, issue, wiki, or logs.

## Persistent source access

The managed company project **MCP Qdrant Hybrid** exposes the source to MCP Engineer:

- Project: `mcp-qdrant-hybrid`.
- Primary workspace: `/paperclip/repos/mcp-qdrant-hybrid` (local Git repository, base `main`).
- Current baseline commit: `a47793facdc9d3e43cc9192c30c75200f3e119a1`.
- Runtime-generated issue worktrees use the project policy (`{{issue.identifier}}`); do not create branches/worktrees manually.
- `HOST-RUNBOOK.md` documents the exact host build/recreate/rollback path. `scripts/mcp-qdrant-empty-smoke.mjs` covers empty → insert/query → delete-last → empty when the shared collection is initially empty.

Agents can read, edit, test, and commit through the managed project. The host Docker socket remains outside agent workspaces; production rebuild/restart is performed by the host operator using the runbook. No Paperclip application code was changed.

## Empty-collection query — fixed and live-verified 2026-10-04

The empty Qdrant collection made LlamaIndex raise `ValueError("Vector store query result should return at least one of nodes or ids.")` while building the retrieval result. MCP sanitized it to the bare `Error executing tool query`. The handler now recognizes that exact empty-result condition, confirms `points_count == 0` using an exact Qdrant count, and returns `[]`; non-empty and unrelated failures are not swallowed.

Deployed image ID: `sha256:381764165e3aa9eb4aa7cefc963bd867a8ccb184e404a7eb67187a1a4305de84`.

Live smoke against production passed:

1. Empty collection query returned `[]` without `isError`.
2. A unique inserted document remained discoverable by hybrid dense+sparse query.
3. Deleting that document returned the collection to zero points; query again returned `[]`.

The smoke removed its unique test document and confirmed `points_count == 0`. Previous Qdrant `get_document`/`delete_document` repairs and cleanup from KOMAA-411 remain intact.

## Tool and data contract

- `query` on no matching points returns an empty result array; successful hybrid results retain `doc_id`, `node_id`, `score`, `text`, and `metadata`.
- `doc_id` is a 32-hex document identifier; underlying Qdrant point IDs are chunk `node_id` UUIDs. Get/delete filter by payload `doc_id`.
- `get_document` on a missing ID reports a readable not-found error; `delete_document` is idempotent.
- Before future changes, read current runtime/collection state and the host runbook. Never use the development Compose stack to deploy production; it starts a separate local Qdrant.