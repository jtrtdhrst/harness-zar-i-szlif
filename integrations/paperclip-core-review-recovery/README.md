# Paperclip Core: stale pre-dispatch review hold

A stopped Harness Engineer run `7f76990f-e4c1-4742-8ecd-a53aa2d3d201` was cancelled for reassignment before any selected runtime, process, remote run or log. Paperclip later recorded `automaticRecovery.replay="blocked"` in a resolved recovery action. `getExecutionBlocker` still projects it as an effective dependency, so native CTO review on `KOMAA-1564` reports `awaiting_external_dependency` although there are zero unresolved issue relations. This is not fixed by resubmitting review, patching issue status or pretending an approval was made.

This patch ONLY suppresses the read-only blocker *projection* when all persisted evidence proves a completely undispatched, stop-confirmed old run; it does not change the recovery action, issue status or independently required review. Any provider event, selected runtime, process PID, external run, nonzero logs, missing signed stop confirmation, wrong scope/owner, or active recovery action **retains the hold**. It is intentionally separate from the adapter-only Hermes source issue `KOMAA-1564` and its [PR #36](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/36).

## Validation

- Pinned base image: `ghcr.io/paperclipai/paperclip:2026.1023.0`.
- Original `server/src/services/execution-blocker.ts` SHA-256: `bccaebea9d6252b1a0f5af0e2b8c669d72a4ce66fdfbbd370ff44a7c99a0d64a`.
- Patched SHA-256: `bcf4e0c859c21828b7d5a2a705cf1163b35839fee0be581ddfa8c654dcc9e78d`.
- Non-cached VPS Docker build: **4/4 tests + TypeScript server typecheck PASS**; test image digest `sha256:e3d95f81912d0f27302e7726c8286f6eaaa37446ccd32c397b7087fff1920197`.
- GitHub Actions additionally performs a source-pinned Docker build, tests and full server dist build.

## Release safety

This image repairs only the Core blocker and does not contain the Hermes adapter from PR #36. **It is not the final migration image.** Independent review must approve this low-level policy logic, then build one unified tagged image from the approved main branch including both source patches, with positive and negative E2E proof. Production Paperclip, production Hermes, its 3.2GB volume and 14 opencode_local agents are NOT changed by this PR. Do not directly patch database rows or impersonate CTO to approve the task.


## H03 review checkout follow-on (KOMAA-1595; unapproved candidate)

This additive `reviewer-checkout.patch` applies **after** the existing pre-dispatch
`overlay.patch`; it does not replace or remove that independently merged fix.
The immutable source is the issue-owned upstream Paperclip worktree commit
`58bed91e27deba8c9420c7e95d09eb0501cc987c`, based on pinned upstream
`1b4c803816e82b0265c8422e1a804327a7ed8c54`.

The patch changes only `server/src/services/issues.ts` and the regression
`server/src/__tests__/issue-stale-execution-lock-routes.test.ts`.
It preserves `in_review` when the configured reviewer checks out a pending
review, checks the exact current stage ID/type and policy participant **in the
atomic database predicate**, and refuses incorrect expected statuses, stale
stages, approval stages and foreign agents. The Dockerfile checks before/after
SHA-256 values for both source files and executes bounded route regression
tests in CI, before server TypeScript compilation.

The issue-owned source tests passed **19/19** targeted checkout regressions.
The separate H03 integration suite completed with exit code zero in an
isolated rerun; a combined run had one intermittent failure and its independent
rerun emitted an asynchronous PostgreSQL deadlock warning. A full server
typecheck was not clean from the source worktree because of missing
`@paperclipai/paperclip-runner` workspace declaration/build artifacts; a
later bounded typecheck timed out. **The GitHub Docker build and its native
CI are required**, and no typecheck PASS is claimed from the worktree.

This is **not** a Hermes authorization release, a Paperclip Core production
deploy, an Opik trace, or a CHO/CTO first-class approval. No existing PR #36
or #48 head is altered. Do not switch agents or re-enable the held
`paperclip-mcp-auto-release.timer` without its own trusted review gate,
approved source promotion and independent production readback.
