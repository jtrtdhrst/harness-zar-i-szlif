# Unified Paperclip Core review-recovery + Hermes adapter image

This image preserves the independently fixed **Paperclip native review blocker**
from [PR #43](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/43)
while adding the Hermes run-scoped MCP adapter from
[PR #36](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/36).
KOMAA-1564 (H01) received an **independent CTO-approved source/security** decision on 2026-11-04; that decision does **not** authorize a merge, production deployment or agent cutover.

Both patches are applied to a single immutable source-pinned base,
`ghcr.io/paperclipai/paperclip:2026.1023.0`.
The Dockerfile uses the **repository root build context**, so the actual
merged source from `integrations/paperclip-core-review-recovery/overlay.patch`
is reused rather than copied/duplicated. Each of the two original source
SHA-256 hashes and both patched output hashes are verified; a mismatch fails
the build.

The image runs the native Core regression suite, the Hermes adapter
regression suite, adapter/server TypeScript checks, and emits the updated
server runtime JavaScript. Last independently verified H01: 114/114 adapter
Vitest tests in issue source, 108/108 in the pinned image, adapter TypeScript
PASS, and 3/3 exact-code-HEAD CI checks SUCCESS. A successful build is not
equivalent to a Paperclip-issued token or a real LLM/Hindsight/Opik run.

## Status and release gate

The canonical status ledger, evidence links, trust boundary, negative-test matrix,
and ordered production/rollback procedure live in
[**Hermes operations and E2E runbook**](../OPERATIONS-STATUS.md).

- H01 source/security approval applies to issue worktree commit
  `792598741832c31d91d74c8de9e787639944d13e` and original reviewed
  PR #36 code SHA `d6a6f5455f9732b17ba00dc163c4c985ca9627ff`.
  Any later documentation-only PR HEAD needs fresh CI/readback before promotion.
- Run an authorized Paperclip issue against a named Hermes profile with a
  short-lived per-run MCP grant; verify Wiki/Skills positive and revoked,
  cross-run/agent denial at the issuer.
- Prove a Hermes-native Hindsight retain + independent-session recall in the
  correct role bank, wrong-bank rejection and matching Opik task_id/run UUID.
- CHO approves a source-controlled tagged release with image-digest readback,
  rollback receipt, and cohort-0 real-agent canary before more agents switch.

Do not run a second Core connected to the production DB and /paperclip volume.
Do not replace the running production image merely because this composite
candidate passes isolated CI.
