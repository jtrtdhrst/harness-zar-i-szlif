# Repository instructions for agents and contributors

This repository owns infrastructure services, standalone integration MCPs, and their operational documentation. The Żar i Szlif product application and its product-specific MCP belong in [`miloszspyrka-code/zar-i-szlif`](https://github.com/miloszspyrka-code/zar-i-szlif); do not move product work here or modify Paperclip Core.

## Before repository changes

1. Load the managed `agent-git-delivery` skill and follow its current version. Its canonical repository-context and delivery contract is `wiki/concepts/agent-git-delivery-policy.md`; do not duplicate that policy here.
2. Read this repository's `README.md`. For release or infrastructure work, also read `docs/COOLIFY-PROJECTS.md`, `docs/RELEASE-POLICY.md`, `ops/release-lanes.json`, and the affected service runbook. Read only the relevant runbooks.
3. Resolve repository and path ownership before editing. General-purpose MCPs and server integrations belong here; product code and product-only MCP code do not.
4. Before the first mutation in an issue/run, attach a bounded `DOC_PREFLIGHT` record to that existing issue or PR with the issue, agent, runId, exact repo and base SHA, read document paths and hashes, target paths, code owner, release lane, live runtime check or `NA`, divergences, and `PASS` or `STOP`. Never invent a read, hash, identity, runtime result, or approval.
5. Treat release-lane inventory as dated evidence. Recheck the current service/runtime and approved lane before any promotion. A source commit, CI pass, health check, or merge alone is not a deployment acceptance.

This preflight is an auditable execution requirement. Do not describe it as enforced by the Paperclip API, GitHub, or an MCP write boundary unless a real fail-closed implementation and authorized negative agent-run test prove that claim.

## Source and release boundaries

- Keep each service's source, build context, persistent data, and release evidence within its existing service boundary. Follow `docs/COOLIFY-PROJECTS.md`.
- Do not add a Worker, PAT, GitHub App, service, or host-wide helper to work around an existing access or release gate.
- Keep runbooks canonical and link to them instead of copying their operational procedures into new documents.
- Preserve existing branches, worktrees, candidate artifacts, and review history. Never bypass native authorization or independent review.
