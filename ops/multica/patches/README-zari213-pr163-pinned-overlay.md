# ZARI-213 — pinned native daemon overlay, NOT a production release

Purpose: unblock **agent-owned** `git push` in the existing native Multica → Hermes → GitHub App credential flow without borrowing the operator's GitHub identity, bypassing HOLD, or changing repositories outside a task's project.

## Exact source provenance

- Existing issue: `ZARI-213`, existing branch `task/zari-213`, prior PR #215 (closed/unmerged).
- Native local Multica baseline commit: `1d2fcff08a65e0037f2a1256994f844fc1388e07`, inspected on the VPS at `/opt/experiments/zari213-pr163-exact-95a7-verify`.
- Apply **only** `zari213-pr163-pinned-overlay.patch` to the *clean tracked tree of that exact commit*; do not apply to upstream `b1ea927` or the running binary.
- SHA-256 of patch bytes: `2e6f64c7a065dabbf27854df626aa5af2fefc3045fd2714f628896a46030ae7c`; 419 lines, 18,715 bytes, seven tracked files; `git apply --reverse --check` passed on reconstructed tree.
- Source merges existing uncommitted scope/fresh-checkout fixes from the protected PR163 baseline and changes `localCloneArgs` to pass `--no-hardlinks` on **all** OSes, with Linux/macOS/Windows tests.
- Isolated candidate built with Go 1.26.9, `CGO_ENABLED=0`, from these exact bytes: SHA-256 `1c900c333da5a437ce80a84dd76b6e56c114c10be0cf2138e7453f8de02e14a9` (local staging, **not** a trusted production artifact).
- Focused tests (native daemon task-scope/checkout and repocache independent objects/fresh fail-closed) PASS. Full independent review, complete isolation E2E and real GitHub write test still required.

## Acceptance and safety

1. Independent CTO must compare pinned baseline, this exact patch, and production's existing security controls; reject source drift.
2. COO must independently approve **specific** reviewed source SHA + binary digest, broker version and a no-active-task maintenance window. The earlier `112d0af9...` upstream-only binary is **explicitly rejected**.
3. Broker must use the project-scoped implementation from the *same reviewed lane*; the currently installed broker is a third, older version. Preserve per-project GitHub App tokens and root-only secrets.
4. After an authorized reversible daemon/broker upgrade, prove `/repo/scope` returns token-bound `workspace_id`, `task_id`, `agent_id`, nonempty `project_id` and precisely one authorized `repo_url` for an active Harness or Product task; missing/foreign tokens and cross-project requests fail closed.
5. A **real Hermes agent**, not the owner connector, must push a non-force task-branch commit and independently read back the new SHA on GitHub. Also prove foreign repository, foreign task and bare-mirror/secret denial. Do not push to `main`, bypass HOLD or deploy Coolify merely to pass this canary.
6. If any acceptance fails, restore prior daemon+broker and preserve HOLD. Do not mark ZARI-213 DONE from build, PR, tests, or healthy process alone.

The patch and these notes are evidence for review, **not release permission**.
