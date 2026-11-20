# GitHub Ops MCP — scoped augmentation (not a deployment controller)

A separate, minimal GitHub MCP endpoint for operations absent from the regular GitHub connector: read branch protection/rulesets/Actions permissions and deployment evidence; preview *already merged* branches without deletion; cancel an allowlisted, SHA-verified in-flight workflow. Workflow dispatch is disabled until it can be atomically bound to an immutable reviewed SHA.

## Fail-closed defaults

- Hard-coded repository ceiling: `miloszspyrka-code/harness-zar-i-szlif`, `miloszspyrka-code/zar-i-szlif`.
- `POST /mcp` requires either a constant-time checked `GITHUB_OPS_CALLER_TOKEN` or a cryptographically verified Cloudflare Access JWT restricted to the configured issuer, application AUD and owner email. The Cloudflare path requires `CF_ACCESS_ISSUER`, `CF_ACCESS_AUD`, `CF_ACCESS_OWNER_EMAIL` and Cloudflare Managed OAuth on the Access application. `GITHUB_TOKEN` is still required to execute real GitHub operations. Never commit secrets, embed them in URLs, or put them in Multica CLI args.
- `GITHUB_OPS_WRITES_ENABLED` defaults to false. `GITHUB_OPS_WORKFLOWS` defaults to `release-lanes-policy.yml` only. Non-atomic branch deletion is not exposed or configurable.
- `GET /health` is a liveness endpoint; `ready=false` explicitly means **not operational**, even if Coolify reports the container healthy.
- No generic shell, no arbitrary GitHub URL, no self-approval, branch protection mutation, auto-merge, token provisioning, Coolify deploy, HOLD bypass or implicit user delegation.
- `github_preview_branch_delete` verifies exact source SHA, a merged PR, a reachable merge commit and no open PR references. It NEVER deletes. GitHub REST `DELETE /git/refs/...` has no expected-SHA conditional delete, so a concurrent push cannot be excluded. The old `github_delete_merged_branch` tool was removed and its legacy call fails closed.
- `github_dispatch_workflow` is NOT exposed. GitHub `workflow_dispatch` with `ref: main` can run a different commit if main advances after checking SHA. Checking the run later detects the problem too late. Calls fail closed before any GitHub request.
- Branch protection/ruleset endpoints may reply HTTP 403 due to GitHub App scopes or private-repository plan limitations. Never treat that as protection enabled.
- All writes must satisfy the separate existing CTO review, release HOLD, CI and operator access boundaries. This service does not enforce the complete GitHub→Coolify promotion policy.

## Run and check

`npm test` — 15 HTTP-level mocked-provider positive/negative tests. These include disabled workflow dispatch, missing authentication and non-atomic branch deletion rejection; they make no real GitHub provider writes.

`PORT=3000 GITHUB_OPS_CALLER_TOKEN=<secure-secret> GITHUB_TOKEN=<scoped-secret> node server.mjs`

Use a Coolify **private, manual** staging application with `base_directory=/github-ops-mcp`, `Dockerfile` build and `is_auto_deploy_enabled=false`. No FQDN, no public port, no production secrets in build args. Do not turn on writes/deletion in a test deployment. Register its private MCP URL in Multica only after independent authorization, a supported secure secret injection path, and test of the exact target runtime's network reachability.

## MCP verification

- `initialize` then `tools/list` (authenticated): seven tools.
- `tools/call` with repo outside ceiling: `REPO_DENIED` without provider traffic.
- Without `GITHUB_TOKEN`: `AUTH_NOT_CONFIGURED` without provider traffic.
- Without caller token or invalid token: 401.
- With a scoped production credential: verify GitHub `repo_info`, `get_deployments` for a known exact SHA, and provider error handling before enabling any write. Independent QA must read back effect and correlate immutable image digest + authenticated live service QA via Coolify.

The current native Multica ZARI-213 isolation HOLD applies: do **not** grant a high-privilege operator server to unisolated agents or move it into production until that trust boundary is independently proven.

## Live Cloudflare staging state (2026-11-20)

- URL: `https://github-ops-mcp.zariszlif.pl/mcp`, behind an owner-only Cloudflare Access app with Managed OAuth.
- Cloudflare Access forwards `Cf-Access-Jwt-Assertion`; the origin validates RS256 signature, issuer, AUD, expiration and exact owner identity against Cloudflare's JWKS. Docker network access does **not** skip JWT checks.
- GitHub Ops MCP is registered in the Multica workspace MCP library but **not assigned to any agent** while ZARI-213 isolation and independent review remain blocked.
- Coolify staging auto-deploy is disabled. Existing main and production containers are unchanged.
- **Status is not ready:** no scoped GitHub API credential has been provisioned; `/health.ready=false`. The server only provides OAuth/MCP discovery and safe structured errors without it.
- Full external OAuth authorization-code login and a real GitHub provider E2E remain unverified; do not report source-only tests or Docker health as operational readiness.
