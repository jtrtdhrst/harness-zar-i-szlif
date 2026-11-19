# ZARI-213 — task-local Hermes SQLite lock sidecars

Status: reviewed source candidate; NOT a production isolation clearance.

## Root cause (2026-11-19)
Multica Core v0.8.1 host checkout commit `b1ea927def6490c43bedff537b6f4ed9a47fa828` only classified `state.db` and `state.db-*` as task-local in `execenv/hermes_home.go`. Hermes also creates `state.db.quarantine.lock` and `state.db.fts_rebuild.lock` (dot suffix). They were mirrored from the shared source profile as symlinks, despite the conversation database being task-local. A live read-only scan found 261 `state.db.quarantine.lock` symlinks across 286 session directories. These symlinks are an isolation defect; they may contribute to native Hermes startup failures, but are not proof that all `blocked` issues share that cause.

## Patch
`zari213-hermes-state-db-locks.patch` changes upstream source and regression tests only:
- explicitly marks both known lock sidecars task-local, while leaving unrelated `state.db.*` files alone;
- on *every* reuse, removes only legacy SQLite lock symlinks by unlinking their local directory entries (not their referenced host targets), including when a state marker already exists; preserves task-local regular lock files; rejects unexpected entry types;
- tests fresh projection, legacy migration, reuse with an existing marker, negative scope, and host-file preservation.

Pinned upstream baseline: `b1ea927def6490c43bedff537b6f4ed9a47fa828` (Multica Core, not the Harness repository). Do not apply to unverified newer checkout; rebase and review it instead.

## Reproducible verification
```sh
git -C /path/to/multica-core rev-parse HEAD
git -C /path/to/multica-core apply --check /path/to/zari213-hermes-state-db-locks.patch
# Only in a disposable worktree based on the pinned upstream commit:
git -C /path/to/disposable-multica-core apply /path/to/zari213-hermes-state-db-locks.patch
cd /path/to/disposable-multica-core/server
go test -count=1 -run 'TestHermesOverlayKeepsSessionDatabaseTaskLocal|TestHermesOverlayMigratesLegacySessionDatabase|TestHermesOverlayReuseDetachesLegacySharedLockLinks|TestHermesStateFamilyClassificationDoesNotMirrorUnrelatedDotNames' ./internal/daemon/execenv
# Run full package as an unprivileged identity (not root; one existing test checks file permissions):
go test -count=1 ./internal/daemon/execenv
```

Host evidence 2026-11-19: targeted Go tests PASS; full execenv binary executed as `multica-zar` returned 0/PASS. Running full package as root fails unrelated pre-existing unreadable-file negative canary (`TestMigrateHermesTaskMemoriesFailureKeepsSource`) because root bypasses file permissions. Candidate binary built with Go 1.26.9 / CGO_ENABLED=0: `/opt/experiments/multica-poc/bin/multica-zari213e-sqlite-locks-20261119`, SHA256 `e5bef09cd00b858ccb1b1c32f4cd415ebb575ffb61d847c221dfe6757dc3a094`. Candidate is STAGED ONLY, daemon still on `multica-zari213d-sqlite-fix-20261118`.

## Controlled release gates
1. Independent CTO exact-head review and tests, plus SHA-bound CI.
2. Compare the candidate against running daemon's host-local SQLite changes; do not overwrite untracked functional fixes.
3. Back up systemd override and binary, validate root-owned Landlock launcher; authorized host operator replaces only approved daemon binary; restart and check healthy.
4. Real two-role native `TOOL_USE`/`TOOL_RESULT` positive own-home and negative foreign-home / shared-lock; verify session state and rollback behavior. If any fail, restore previous binary and systemd override.
5. Per-role Hermes model credential broker, shared `.hermes/auth.json`/`.env` symlink elimination and independent grants remain separate security blockers. Do not lift ZARI-213 HOLD, grant broad write access or mark full ZARI-240 DONE based on this patch alone.

No tokens, provider credentials or private runtime data are stored here.
