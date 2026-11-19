---
title: Architecture graph and migrated Wiki require evidence and provenance
status: accepted
date: 2026-11-09
---
# ADR 002: Historical Paperclip Wiki is not an active agent policy

## Context
Paperclip Wiki contained 108 pages, including archived agent instructions, temporary execution guidance and dated architecture assertions. Repowise v0.60.1 derives edges from Git and may match unrelated generic HTTP endpoints such as `GET /health`.

## Decision
Preserve all 108 historical pages in exactly one of the two repo-specific archives (subject to explicit PII redaction), track source paths/hashes and mark historical status. Operational authority comes from current user decisions, repo source, exact SHA and running service evidence. Treat inferred graph edges as hypotheses until supported by real provider/consumer code and configuration.

## Consequences
Agents must not execute archived Paperclip role policies as Multica/Hermes policies. A successful Repowise MCP request confirms retrieval, not a fully accurate system model or an E2E deployment.

## Evidence and scope
- `docs/knowledge/PAPERCLIP-ARCHIVE-INDEX.md` and `docs/knowledge/migration-manifest.json`.
- `docs/knowledge/REPOWISE-E2E-STATUS.md`.
- Scope: entire Harness repository and cross-repo agent queries.
