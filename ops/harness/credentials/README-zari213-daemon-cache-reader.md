# ZARI-213 — daemon Git cache read-only identity

The live broker at `/usr/local/libexec/multica-git-credential-broker.py` authenticates real Multica task children via `SO_PEERCRED` and process ancestry. The daemon's own `git fetch` / `git clone` runs as a direct child with no task identity, so legitimate `multica repo checkout` cannot refresh a private GitHub repository. E2E Harness run `01a1f8f1-62ac-7d96-aba6-efc8f33dcf67` reproduced `no_active_multica_task`; also identified the separate Landlock `.gitconfig` denial in PR #170.

The daemon-cache credential is a separately minted, repository-restricted GitHub App installation token with exactly `contents=read` and `metadata=read` for the two allowlisted repositories. This is **not** the task reviewer token (which has `pull_requests=write`). The tracked `multica-zar-github-app-refresh.py` source introduces `cache-reader` without changing the permissions of any existing agent role. The broker checks `role`, full repository set and exact permission dictionary on each cache-reader token before returning credentials. An empty/missing grant fails closed; no borrowed write-capable fallback.

Authorization additionally demands exact helper → Git remote transport → daemon Git process ancestry, real /proc executable identities and a strict helper argv script path (no substring match, Python -c, generic shell, arbitrary -c Git configuration, push or `op=token`).

## Project-scoped task tokens (2026-11-21)

The broker no longer hands a task the workspace-wide `implementer`/`reviewer`/
`release`/`runner` token. For a task with a project claim it resolves the token
against the live daemon `/repo/scope` endpoint and selects the repository-only
variant: `implementer-harness`, `implementer-product`, and the same suffixes for
`reviewer`, `release` and `runner`. A request for a repository outside the
task's `RepoURLs` is denied before any token is loaded; an empty, malformed or
unreachable scope fails closed. Project tasks with two repository claims also fail
closed at both the daemon checkout boundary and credential broker. No
workspace-wide credential may be borrowed by a project task.

This closes the direct `git clone`/`git fetch` path around project-scoped
`repo checkout`: the returned credential can read only the task's project
repository. It does not by itself prove that the running daemon enforces the
claim; the live two-role positive/negative E2E below remains mandatory.

Offline suite: **52/52 PASS** as a non-root user on 2026-11-21, covering the
daemon-cache ancestry, exact dispatch/shell chain, project-scoped role
selection, foreign-repository denial, fail-closed scope errors, Landlock and
refresh token-file checks. Offline tests do not establish that the deployed
broker can read from GitHub, that the scoped tokens are minted, or that
cross-task leaks are impossible.


Source expected before SHA256: `712d30ad25413d51e961fbce788f4ad6ee932be54eac8c7680aef5e80d3e225d`.

Candidate source SHA256 MUST be computed and recorded from the exact CTO-approved PR HEAD at install time; the earlier 3123e250 candidate is obsolete.\n
Offline validation (non-root): `python3 -B -m unittest discover -s ops/harness/credentials -p 'test_zari213_*.py' -v`. The original root broker must remain in use until independent exact-HEAD approval and a permitted root-controlled install with rollback. Do not disable the ZARI-213 security HOLD or mount a shared token into a task.
