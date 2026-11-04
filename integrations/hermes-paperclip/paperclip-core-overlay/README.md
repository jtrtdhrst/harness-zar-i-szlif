# Unified Paperclip Core review-recovery + Hermes adapter image

This image preserves the independently fixed **Paperclip native review blocker**
from [PR #43](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/43)
while adding the Hermes run-scoped MCP adapter from
[PR #36](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/36).
It does **not** merge or bypass the native review decision for KOMAA-1564.

Both patches are applied to a single immutable source-pinned base,
`ghcr.io/paperclipai/paperclip:2026.1023.0`.
The Dockerfile uses the **repository root build context**, so the actual
merged source from `integrations/paperclip-core-review-recovery/overlay.patch`
is reused rather than copied/duplicated. Each of the two original source
SHA-256 hashes and both patched output hashes are verified; a mismatch fails
the build.

The image runs the native Core regression suite, the Hermes adapter
regression suite, adapter/server TypeScript checks, and emits the updated
server runtime JavaScript. A successful build is not equivalent to a
Paperclip-issued token or a real LLM/Hindsight/Opik run.

## Release gate

- PR #36 must receive a genuine independent CTO decision on its exact head.
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
