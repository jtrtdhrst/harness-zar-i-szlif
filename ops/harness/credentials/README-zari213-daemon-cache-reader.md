# ZARI-213 — daemon Git cache read-only identity

The live broker at `/usr/local/libexec/multica-git-credential-broker.py` authenticates real Multica task children via `SO_PEERCRED` and process ancestry. The daemon's own `git fetch` / `git clone` runs as a direct child with no task identity, so legitimate `multica repo checkout` cannot refresh a private GitHub repository. E2E Harness run `01a1f8f1-62ac-7d96-aba6-efc8f33dcf67` reproduced `no_active_multica_task`; also identified the separate Landlock `.gitconfig` denial in PR #170.

This scoped broker change retains existing task-specific implementer/reviewer/release token selection. For an unaffiliated process, only a **Git fetch/clone/ls-remote process launched directly by the validated multica-zar-daemon** and reached via the trusted helper may request a credential, and it receives the existing `reviewer` token (GitHub App `contents=read`, no Git content writes). Cache credentials are denied for push, unknown helper, generic shell, invalid process ownership, and `op=token`; repository allowlist remains enforced. Because GitHub reviewer token also has `pull_requests=write`, this special-case is accepted only after independent review proves token cannot escape to an untrusted agent, and a native read+negative E2E on the live VPS. It is **not** a generic GitHub MCP grant.

Source expected before SHA256: `712d30ad25413d51e961fbce788f4ad6ee932be54eac8c7680aef5e80d3e225d`.

Candidate expected SHA256: `3123e25074a497e72090fbe64a77d2d069e8577ce3ee04e6ee20410271b2ebc5`.

Offline validation: `python3 -m unittest discover -s ops/harness/credentials -p 'test_zari213_daemon_cache_reader.py' -v`. The original root broker must remain in use until independent exact-HEAD approval and a permitted root-controlled install with rollback. Do not disable the ZARI-213 security HOLD or mount a shared token into a task.
