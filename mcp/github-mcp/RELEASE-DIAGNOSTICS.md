# GitHub Ops MCP — release diagnostics

The existing PR #204 / ZARI-263 adds three read-only tools:
- github_get_effective_main_rules: effective rules on main, not merely ruleset names.
- github_list_environments: bounded deployment environment and protection policy metadata; no secrets.
- github_get_pr_reviews: exact expected PR head SHA, bounded review evidence, stale-head refusal and post-read SHA recheck.

All three use the existing allowlisted repository reader. Provider permission errors remain errors; a truncated list or unknown policy is not proof of release readiness. These tools never approve, change policies, merge or deploy. Existing write gates and GitHub protections remain unchanged.

The Product release migration is tracked in ZARI-269 and Product PR #190. The GitHub Ops MCP source change requires independent review, CI and authorized deployment before claiming these tools are available in production. RepoWise indexes merged source, not an unmerged PR.
