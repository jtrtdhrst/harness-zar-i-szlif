# ZARI-213 — upstream Multica task/project checkout ACL

- Applies to local Multica security-fix source **`1d2fcff`** at `/opt/experiments/multica-zari213-exact`, not the older unpatched `b1ea927` checkout.
- Patch: `zari213-project-claim-repo-checkout.patch`; apply from the source repository root with `git apply --check <patch>` then `git apply <patch>`. It modifies only four files under `server/internal/daemon/`.
- Threat: when a project's `github_repo` resources are empty, the Multica server intentionally supplies workspace repositories as fallback context, but this fallback must **not** authorize cross-project `repo checkout` in the daemon.
- Fix: the active task's authenticated `RepoURLs` scope intersects the claimed repository list with its explicit `ProjectResources` `github_repo` entries when `ProjectID` is present. An absent/malformed manifest fails closed. Unprojected tasks preserve workspace repository semantics. Previously supported scp/HTTPS aliases remain; exact local-path grants remain supported.
- Tests: Go 1.26.9, offline `go test ./internal/daemon -run 'TestZARI213|TestRepoCheckout' -count=1 -timeout 120s` PASS (3.336s) on a fresh, separate clone after `git apply --check` and `git apply`; `git diff --check` PASS (2026-11-19). Affected upstream files: daemon.go, health.go, health_test.go, zari213_repo_scope_test.go.
- The older staged binary built before this local-path correction is OBSOLETE. No updated production binary has been built or installed from this patch. Live native canary is still required.
- Scope: only checkout admission. It does not address shared Codex OAuth, the broker's native-provider migration, or task session isolation. Do not interpret unit tests as production agent E2E. Rollback via the pinned prior daemon binary after a controlled restart if the post-release canaries fail.
- Required live validation: same-project positive checkout and cross-project negative checkout with actual task-scoped native CLI credentials; exact binary digest and separate CTO review; no secret values printed; no creation of unrelated project worktrees during negative denial.

## Reviewer correction — exact local paths

The prior candidate rejected a project-scoped absolute local repository path even when exactly listed in both the trusted task claim and a `github_repo` ProjectResource. The corrected helper uses a non-empty repo identity for remote origins or a `local:`-prefixed key only for absolute, lexically clean local paths. An empty/relative/unclean/unclaimed path is denied; a matching absolute clean path is admitted. Added positive and negative exact-match, prefix, relative and traversal tests. This is a source-level correction, NOT evidence that the running daemon enforces it.

Exact corrected patch SHA256: `6dea7b5904177a9cb5c002b66acc6c706a6d7894a07343b87c4f9b533a59f461`, 8,658 bytes. Validated against upstream base `1d2fcff` in isolated `/tmp/zari213-pr163-test.Fg7lY9/verify`. Current live daemon executable is a separately built SQLite-modified binary: do not replace it blindly with a build from older upstream source; preserve its existing runtime modifications and roll back on failed native canaries.
