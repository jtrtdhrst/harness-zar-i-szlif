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
