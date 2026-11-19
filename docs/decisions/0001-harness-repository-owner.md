---
title: Harness repository boundary
status: accepted
date: 2026-11-09
---
# ADR 001: Harness owns independent services and agent infrastructure

## Context
The root README at GitHub SHA `fe2839d7e41ee3b581f7bf92857a39b1106098f6` states that Harness owns standalone MCP, agent runtime integrations, operations and infrastructure. Product-specific MCP belongs to Product.

## Decision
Use `miloszspyrka-code/harness-zar-i-szlif` as the source repository for Hermes, Multica integration contracts, general MCP servers, Hindsight/Opik integration, Coolify/Cloudflare deployment controls and related operating documentation.

## Consequences
Each service has independent release evidence; a changed Harness source SHA alone does not imply all running images were rebuilt. Product and Harness must be separately indexed under the shared Repowise workspace.

## Evidence and scope
- Harness root `README.md` at SHA `fe2839d7`.
- `docs/knowledge/CROSS-REPO-BOUNDARY.md`.
- Scope: `integrations/`, `ops/`, `coolify-mcp/`, `opik-mcp/`. The former root `paperclip-mcp/` path was removed in the repository cleanup; this ADR preserves its historical context.
