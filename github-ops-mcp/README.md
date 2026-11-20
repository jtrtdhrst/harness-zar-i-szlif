# GitHub Ops MCP — scoped augmentation (not a deployment controller)

A separate, minimal GitHub MCP endpoint for operations absent from the regular GitHub connector: read branch protection/rulesets/Actions permissions and deployment evidence; preview/delete *already merged* branches; dispatch a specifically allowlisted GitHub Actions workflow; cancel an allowlisted, SHA-pinned in-flight workflow.

## Fail-closed defaults

- Hard-coded repository ceiling: `miloszspyrka-code/harness-zar-i-szlif`, `miloszspyrka-code/zar-i-szlif`.
- `POST /mcp` always needs `GITHUB_OPS_CALLER_TOKEN`; `GITHUB_TOKEN` needs an appropriately limited GitHub App installation credential or fine-grained PAT. Never put either in git, a URL or Multica CLI args.
- `GITHUB_OPS_WRITES_ENABLED` defaults to false, `GITHUB_OPS_BRANCH_DELETION` defaults to false, and **`GITHUB_OPS_DELETE_ALLOWLIST` defaults to empty** (comma-separated exact entries like `miloszspyrka-code/harness-zar-i-szlif:fix/retired@<40-character SHA>`). `GITHUB_OPS_WORKFLOWS` defaults to `release-lanes-policy.yml` only. An enabled deletion flag without an exact matching approval cannot delete anything.
- `GET /health` is a liveness endpoint; `ready=false` explicitly means **not operational**, even if Coolify reports the container healthy.
- No generic shell, no arbitrary GitHub URL, no self-approval, branch protection mutation, auto-merge, token provisioning, Coolify deploy, HOLD bypass or implicit user delegation.
- A branch deletion needs **both write gates**, an explicit exact `repo:branch@sha` approval in `GITHUB_OPS_DELETE_ALLOWLIST`, and a verified merged PR whose precise head SHA matches the branch. The PR merge commit must be reachable from current `main`, including squash-merge cases. Open PR bases/heads, protected branches, special release/hold/operator/staging prefixes and the live Coolify `ZARI-155` ref are rejected. Deletion rechecks SHA and open PRs, then reads back that the ref is absent. **Coolify bindings cannot be verified solely from GitHub:** the operator must check live Coolify inventory before adding an approval. GitHub DELETE has no atomic lease; quiescent exact-SHA branches only.
- Branch protection/ruleset endpoints may reply HTTP 403 due to GitHub App scopes or private-repository plan limitations. Never treat that as protection enabled.
- All writes must satisfy the separate existing CTO review, release HOLD, CI and operator access boundaries. This service does not enforce the complete GitHub→Coolify promotion policy.

## Run and check

`npm test` — 12 HTTP-level mocked-provider positive/negative tests (verified 12/12 on the exact GitHub branch code in an isolated network namespace, with a fake GitHub API and no production writes).

`PORT=3000 GITHUB_OPS_CALLER_TOKEN=<secure-secret> GITHUB_TOKEN=<scoped-secret> node server.mjs`

Use a Coolify **private, manual** staging application with `base_directory=/github-ops-mcp`, `Dockerfile` build and `is_auto_deploy_enabled=false`. No FQDN, no public port, no production secrets in build args. Do not turn on writes/deletion in a test deployment. Register its private MCP URL in Multica only after independent authorization, a supported secure secret injection path, and test of the exact target runtime's network reachability.

## MCP verification

- `initialize` then `tools/list` (authenticated): nine tools.
- `tools/call` with repo outside ceiling: `REPO_DENIED` without provider traffic.
- Without `GITHUB_TOKEN`: `AUTH_NOT_CONFIGURED` without provider traffic.
- Without caller token or invalid token: 401.
- With a scoped production credential: verify GitHub `repo_info`, `get_deployments` for a known exact SHA, and provider error handling before enabling any write. Independent QA must read back effect and correlate immutable image digest + authenticated live service QA via Coolify.

The current native Multica ZARI-213 isolation HOLD applies: do **not** grant a high-privilege operator server to unisolated agents or move it into production until that trust boundary is independently proven.