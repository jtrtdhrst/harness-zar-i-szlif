# GitHub Ops MCP — release diagnostics

The existing PR #204 / ZARI-263 adds three read-only tools:
- github_get_effective_main_rules: effective rules on main, not merely ruleset names.
- github_list_environments: bounded deployment environment and protection policy metadata; no secrets.
- github_get_pr_reviews: exact expected PR head SHA, bounded review evidence, stale-head refusal and post-read SHA recheck.

All three use the existing allowlisted repository reader. Provider permission errors remain errors; a truncated list or unknown policy is not proof of release readiness. These tools never approve, change policies, merge or deploy. Existing write gates and GitHub protections remain unchanged.

The Product release migration is tracked in ZARI-269 and Product PR #190. The GitHub Ops MCP source change requires independent review, CI and authorized deployment before claiming these tools are available in production. RepoWise indexes merged source, not an unmerged PR.

## Reader recovery — 2026-11-27

Production BGH returned AUTH_FILE_EXPIRED after the legacy Multica-wide refresher was removed. The existing reviewed main reader mint and atomic projection functions restored live read-only GitHub calls, without renewing the writer grant. The branch-deletion preview still fails MERGE_NOT_VERIFIED on the old production implementation. The new explicit `--github-ops-reader-only` mode is a candidate for a single BGH-scoped systemd schedule, independent of Multica agent credentials; it does not activate or renew writer/runner/release grants. Do not install the legacy all-role service as a side effect. Before installation: independent exact-head review, approved source merge, verified service/volume ownership, CI and controlled rotation readback. No release or write authorization is implied.

The proposed native systemd schedule is `ops/systemd/github-ops-reader-refresh.service` and `ops/systemd/github-ops-reader-refresh.timer`. Install the exact reviewed main versions of the existing three credential helper files into the root-owned libexec directory before enabling the timer. Never enable the removed all-role timer. Keep the existing writer grant disabled/expired until independently authorized; this schedule does not issue it. Verify the timer's successful exit, expiry advancement over consecutive rotations, same-scope BGH calls and unauthorized write refusal. Record installation and rollback separately from the OCI image release.
