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


## H03 independent reviewer checkout and rework repair (KOMAA-1595)

This additive `reviewer-checkout.patch` applies **after** the existing approved
pre-dispatch `overlay.patch`. It does not delete or duplicate that patch.

**Exact issue-owned source:** upstream Paperclip pinned base
`1b4c803816e82b0265c8422e1a804327a7ed8c54` to Core candidate
`78ac75e5178f2036ff01561c096967951f529bb3`. The patch includes five files:

- `server/src/services/issues.ts`: fail-closed atomic reviewer admission,
  exact observed stage ID, configured stage type/agent in executionPolicy,
  and an explicit FALSE predicate when no authorized checkout status remains.
- `server/src/routes/issues.ts`: passes the server-observed review-stage
  snapshot, not a caller-supplied stage or fabricated grant.
- `server/src/services/heartbeat.ts`: keeps internally authorized
  resolved-interaction continuation separate from reviewer checkout.
- `server/src/__tests__/issue-stale-execution-lock-routes.test.ts`:
  positive admission plus wrong-agent, stale-stage, expected-status,
  approval-stage, empty-predicate and resumed-interaction cases.
- `server/src/__tests__/issue-h03-false-progress-rework.integration.test.ts`:
  independent Core H03 rework and dependency regression coverage.

**Verified in the isolated issue-owned Core worktree, exact source SHA above:**
25 of 25 focused embedded-PostgreSQL tests PASS (no skips), one Vitest
worker; server `tsc --noEmit` PASS after TypeScript workspace dependency
build; `git diff --check` PASS. A standalone full runner/Rust binary build
was not performed on the host (Cargo unavailable). The Dockerfile additionally
checks source-file SHA-256 **before and after** patch application, refuses
unknown upstream drift, runs PostgreSQL tests as a non-root user, and fails if
any of 25 tests are skipped. GitHub CI/Docker build must be verified separately
at the **final PR head**; historical test passes do not substitute for that.

**Not authorized for release:** `KOMAA-1595` still requires a persisted
independent CTO first-class approval bound to the exact source SHA.
Prior CTO `changes_requested` and the native reviewer-participant drift remain
open; a positive review comment is not an approval. GitHub PR #57 is
unmerged, and this candidate is not a production deploy. The separate H03 MCP
control-plane PR #48 and Hermes adapter/gateway PR #36 remain distinct.
Real Paperclip-issued short-lived per-run Named MCP Wiki/Skills, VAI memory
isolation/recall, Opik same-run trace, immutable image digest, production
readback and rollback are all required before Hermes cohort migration.
The Paperclip MCP auto-release timer is intentionally disabled pending the
trusted independent review attestation gate in PR #55; never re-enable it on
the strength of GitHub CI alone.

## Legacy changes_requested hold reconciler (2026-11-06)

A resolved `issue_recovery_actions` record retained `automaticRecovery.replay="blocked"` for a legacy `legacy_disposition_repair_suppressed` run (`2ba4171b-4421-40d2-877f-9ed629f082bd`) which had no process PID, no process start, no external run, no logs, and only lifecycle events. On `KOMAA-1512`, this stale read-only projection prevented all new issue-scoped execution despite a formal independent CTO `changes_requested` decision and an unblocked dependency graph.

The additive `reconciliation-overlay.patch` is **strictly gated** to this precise non-dispatched legacy failure class, resolved recovery, status `todo|in_progress`, an existing formal `changes_requested` decision, and an owner different from the cancelled legacy run. It retains all recovery history and reviewer decisions. Any provider event, process marker, nonempty logs, mismatch, active action, or different cancellation signature retains the no-replay hold.

**VPS source/build:** `/opt/paperclip-releases/core-h03-reconciliation-20261106/`. Built `local/paperclip-core-h03-reconciliation:20261106` from local pinned H03 candidate, digest `sha256:d282c854c6ec4d2f9adaa95461595e94cce5dc0774706c07eb948a3bdd44c569`; **32/32 unit/integration tests**, zero skipped, TypeScript noEmit and emitted server dist passed. The corresponding GitHub Dockerfile integrates the additive patch after both previous overlays; its own CI must independently pass before treating the Git commit as a build attestation.

**Production readback:** Coolify Paperclip Core healthy, HTTP 200, zero restarts. After release, native Paperclip MCP confirmed `KOMAA-1512` issue-scoped CHO run `89300c74-ddf5-4813-a8a5-a95c99dbfe3e`, and both `checkoutRunId` and `executionRunId` matched. This is a proven issue-bound execution recovery, **not** evidence of completed Hermes/VAI/Opik E2E or a first-class final independent review.

**Rollback:** previous healthy image `local/paperclip-core-h03-candidate:56204bc9` / `sha256:ea292ecf0230fcf1429430df604c2c5cc0d398ac67fb9f254b28b92199f234bd`, and saved exact Coolify compose state in `/opt/paperclip-releases/core-h03-reconciliation-20261106/docker-compose.before.yml`. No direct database record changes or permission bypass were used to resolve the no-replay hold. Do not migrate the 14 Hermes profiles on this evidence alone.

## Recovery of a dropped review wake after implementor lease release (2026-11-06)

A reproduced live failure occurred independently for Product `KOMAA-1616` and
Harness `KOMAA-1617`: the coder entered `in_review` but the normal
`execution_review_requested` wake for CTO/CHO was recorded as
`execution_reconciliation_required` while the coder's workspace lease was
still being released. Later, zero runtime leases remained, the reviewer was
`idle/ready`, and yet there was no reviewer run or review decision. Existing
reconciliation skipped pending reviewers with **no previous reviewer run**.

The additional `review-wake-recovery.patch` preserves the exact server-issued
skipped wake (stage ID, stage type, reviewer ID), requires the live stage to
remain pending, requires absence of any execution blocker, and queues **one
normal authorized reviewer wake** with an exact-stage idempotency key. It never
marks a task approved, changes code-owner roles, or replays an old stage.

Evidence: isolated disposable image `local/paperclip-review-recovery:4f05e290`,
actual embedded-PostgreSQL Vitest: **two selected positive/negative cases
passed**, no failed case; 400 unrelated tests in the large recovery test file
were intentionally filtered out. The patch was also replayed against the
original pinned image bytes using `git apply --check`, `git apply`, and
byte-for-byte comparison. The new Dockerfile layer pins original/patched
SHA-256 and runs those focused regression cases in CI.

**Release is NOT approved by these tests.** Native first-class CTO review
for the Core change remains necessary, the image must be built from the
merged reviewed source, and production E2E still requires a reviewer run,
a genuine decision, exact-SHA deployment and rollback. No Paperclip MCP was
used for diagnosis or this patch.
