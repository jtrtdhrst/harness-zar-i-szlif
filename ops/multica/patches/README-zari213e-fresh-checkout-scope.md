# ZARI-213e — fresh checkout fails closed and exposes task repo scope

Status: reviewed source candidate; live acceptance still required.

## Root cause
The daemon's `repo/checkout` path treated a failed `git fetch origin` as a
warning. A `--fresh` checkout therefore exited 0 from the daemon's cached bare
mirror and produced a worktree that looked current while `origin/main` was
behind GitHub. The same daemon state also had no trusted way for the root Git
credential broker to learn the active task's project-scoped repository claim,
so the broker could only authorize by agent role, not by project.

## Patch
`zari213e-fresh-checkout-scope.patch` changes upstream source and regression
tests only:

- `CreateWorktreeContext` returns an error when `params.Fresh` is set and the
  remote fetch fails; the cached copy is never returned as a successful fresh
  checkout. Non-fresh reused checkouts keep their existing `fetch_error`
  behaviour.
- Hermes tasks use isolated Git metadata (`MULTICA_REPO_CHECKOUT_MODE=isolated`),
  so the task-local `.git` is readable under Landlock instead of pointing into
  the denied shared `.repos` mirror.
- the active checkout claim carries `ProjectID`, and `GET /repo/scope` returns
  the token-bound `workspace_id`, `task_id`, `project_id`, `agent_id` and
  `repo_urls` to the local root broker. It is authenticated by the same task
  bearer token as `/repo/checkout` and exposes no secret.
- the broker uses that claim to select a project-scoped token role and denies a
  repository outside the task's project even when it is on the workspace union.
- the refresh service mints `*-harness` and `*-product` roles in addition to
  the existing broad roles, so an implementer/reviewer/release/runner token can
  be restricted to exactly one repository.

## Verification (offline)
Baseline: `zari213-pr163-exact-95a7-verify` (the source of the running
`multica-zari213-pr163-reviewed-20261120` binary), Go 1.26.9, CGO disabled.

```sh
cd server
go test -count=1 -run 'TestCreateWorktreeFreshFailsWhenFetchFails|TestCreateWorktreeReportsFailedFetch' ./internal/daemon/repocache
go test -count=1 -run 'TestZARI213' ./internal/daemon
go test -count=1 -run 'TestRepoCheckout' ./internal/daemon
```

The Python isolation suite now has **52/52 PASS** as an unprivileged user,
covering the daemon-cache ancestry, exact shell/dispatcher admission, project
role selection, foreign-project denial, task-scope mismatch denial and the
existing Landlock/config/token ACLs.

## Live release gates
1. Independent exact-SHA code review and trusted CI.
2. Install the new daemon binary only after checking no active task; keep the
   previous binary and systemd drop-in for rollback.
3. Install the new broker and refresh files, run one token refresh, restart the
   broker, and verify the installed source hashes.
4. Native Product and Harness task runs must prove: own-project fresh checkout
   reaches GitHub main; foreign-project `repo checkout` and direct Git clone
   are denied; foreign task roots and bare mirrors are unreadable; role token
   files and other secrets are unreadable; rollback restores the previous
   binary and broker.
5. Do not mark full ZARI-213 closure from unit tests, a merged PR or one role's
   canary alone.
