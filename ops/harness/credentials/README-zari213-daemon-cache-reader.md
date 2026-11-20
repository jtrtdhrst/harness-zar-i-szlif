# ZARI-213 — daemon Git cache read-only identity

The live broker at `/usr/local/libexec/multica-git-credential-broker.py` authenticates real Multica task children via `SO_PEERCRED` and process ancestry. The daemon's own `git fetch` / `git clone` runs as a direct child with no task identity, so legitimate `multica repo checkout` cannot refresh a private GitHub repository. E2E Harness run `01a1f8f1-62ac-7d96-aba6-efc8f33dcf67` reproduced `no_active_multica_task`; also identified the separate Landlock `.gitconfig` denial in PR #170.

The daemon-cache credential is a separately minted, repository-restricted GitHub App installation token with exactly `contents=read` and `metadata=read` for the two allowlisted repositories. This is **not** the task reviewer token (which has `pull_requests=write`). The tracked `multica-zar-github-app-refresh.py` source introduces `cache-reader` without changing the permissions of any existing agent role. The broker checks `role`, full repository set and exact permission dictionary on each cache-reader token before returning credentials. An empty/missing grant fails closed; no borrowed write-capable fallback.

Authorization additionally demands exact helper → Git remote transport → daemon Git process ancestry, real /proc executable identities and a strict helper argv script path (no substring match, Python -c, generic shell, arbitrary -c Git configuration, push or `op=token`). Task-specific implementer/reviewer/release selection is unchanged. Because the helper must receive an ephemeral credential for Git, independent review and **actual task isolation negative E2E** remain mandatory before any production install or HOLD change.

All three code files were compile-checked; **18/18 synthetic unit tests PASS** from exact GitHub HEAD `82b4e8318423428bbf970b843dc49da23943268a` on 2026-11-20 under a non-root isolated test directory. They do **not** establish that the deployed broker can read from GitHub, that the new token is minted, or that cross-task leaks are impossible.


Source expected before SHA256: `712d30ad25413d51e961fbce788f4ad6ee932be54eac8c7680aef5e80d3e225d`.

Candidate source SHA256 MUST be computed and recorded from the exact CTO-approved PR HEAD at install time; the earlier 3123e250 candidate is obsolete.\n
Offline validation: `python3 -m unittest discover -s ops/harness/credentials -p 'test_zari213_daemon_cache_reader.py' -v`. The original root broker must remain in use until independent exact-HEAD approval and a permitted root-controlled install with rollback. Do not disable the ZARI-213 security HOLD or mount a shared token into a task.
