# GitHub Ops MCP — scoped augmentation (not a deployment controller)

A separate, minimal GitHub MCP endpoint for operations absent from the regular GitHub connector: read branch protection/rulesets/Actions permissions and deployment evidence; preview and delete *already merged* branches with an expected-SHA lease (never a bare REST delete); cancel an allowlisted, SHA-verified in-flight workflow. Workflow dispatch is disabled until it can be atomically bound to an immutable reviewed SHA.

## Fail-closed defaults

- Hard-coded repository ceiling: `miloszspyrka-code/harness-zar-i-szlif`, `miloszspyrka-code/zar-i-szlif`.
- `POST /mcp` requires either a constant-time checked `GITHUB_OPS_CALLER_TOKEN` or a cryptographically verified Cloudflare Access JWT restricted to the configured issuer, application AUD and owner email. The Cloudflare path requires `CF_ACCESS_ISSUER`, `CF_ACCESS_AUD`, `CF_ACCESS_OWNER_EMAIL` and Cloudflare Managed OAuth on the Access application. `GITHUB_TOKEN` is still required to execute real GitHub operations. Never commit secrets, embed them in URLs, or put them in Multica CLI args.
- `GITHUB_OPS_WRITES_ENABLED` defaults to false. `GITHUB_OPS_WORKFLOWS` defaults to `release-lanes-policy.yml` only. `GITHUB_OPS_PUSH_TOKEN` is a separate, repo-scoped, short-lived credential used **only** by the branch-delete lease; without it deletion fails closed. `GITHUB_OPS_PINNED_BRANCHES` lists branches a live Coolify application tracks (default `feat/github-ops-mcp-20261120`); those are refused even when everything else passes. Keep it in sync with `ops/release-lanes.json`.
- `GET /health` is a liveness endpoint; `ready=false` explicitly means **not operational**, even if Coolify reports the container healthy.
- `tools/call` always returns `structuredContent` as a JSON **object**, never a bare array. GitHub list endpoints are wrapped with their own key and a `count` (`{deployments:[...],count}` / `{rulesets:[...],count}`), so an empty result is an empty list inside an object. A provider reply that is not a list fails closed (`DEPLOYMENTS_INVALID` / `RULESETS_INVALID`) instead of being emitted as a non-conforming payload.
- No generic shell, no arbitrary GitHub URL, no self-approval, branch protection mutation, auto-merge, token provisioning, Coolify deploy, HOLD bypass or implicit user delegation.
- `github_preview_branch_delete` verifies exact source SHA, a merged PR whose head SHA is exactly this branch head, a reachable merge commit, no open PR reference, no protection and no repository rules. It NEVER deletes. `github_delete_merged_branch` performs the same checks and then deletes **through the git protocol with an expected-SHA lease**: `git push --force-with-lease=refs/heads/<branch>:<expected> <remote> :refs/heads/<branch>`. The receive-pack delete command carries the old oid, so a push that lands after verification makes the server reject the lease (`STALE_LEASE_REJECTED`) — the ref and the concurrent commit survive. This replaces the unsafe REST `DELETE /git/refs`, which has no expected-SHA precondition. The command is an argv list (no shell), the push token is passed in the child environment (never argv, never a URL), and the result is read back: HTTP 404 afterwards, otherwise `DELETE_NOT_CONFIRMED`.
- `github_dispatch_workflow` is NOT exposed. GitHub `workflow_dispatch` with `ref: main` can run a different commit if main advances after checking SHA. Checking the run later detects the problem too late. Calls fail closed before any GitHub request (`TOOL_UNKNOWN`, zero provider traffic). No tool advertises a `workflow` input any more.
- A client that still lists `github_dispatch_workflow` has a stale cached tool table, not a live capability. The server never re-adds it; reconcile by re-initializing/re-registering the MCP server in the client (re-read `tools/list`) and confirm the advertised count is 8. That reconciliation is a client/connector-owner action, not a server change.
- Branch protection/ruleset endpoints may reply HTTP 403 due to GitHub App scopes or private-repository plan limitations. Never treat that as protection enabled.
- All writes must satisfy the separate existing CTO review, release HOLD, CI and operator access boundaries. This service does not enforce the complete GitHub→Coolify promotion policy.

## Run and check

`npm test` — 29 HTTP-level and local-git positive/negative tests. These include disabled workflow dispatch, missing authentication, fail-closed branch deletion (writes disabled, missing push credential, pinned branch, stale SHA, protection, repository rules, unknown rule state, no merged PR), and a schema-invariant regression that every advertised tool returns object `structuredContent` for empty and non-empty GitHub lists. The lease tests run against a throwaway local bare repository: a stale expected SHA is rejected and the ref survives; the exact SHA deletes it; a push that lands between verification and delete is refused by the lease. A rules endpoint that answers 403 "Upgrade to GitHub Pro" (private repo, no rulesets possible) is accepted only together with `protected: false`; any other 403 stays fail-closed. They make no real GitHub provider writes.

`PORT=3000 GITHUB_OPS_CALLER_TOKEN=<secure-secret> GITHUB_TOKEN=<scoped-secret> node server.mjs`

Deletion additionally needs the `git` binary in the image (the Dockerfile installs it) and a separate `GITHUB_OPS_PUSH_TOKEN`.

Use a Coolify **private, manual** staging application with `base_directory=/github-ops-mcp`, `Dockerfile` build and `is_auto_deploy_enabled=false`. No FQDN, no public port, no production secrets in build args. Do not turn on writes/deletion in a test deployment. Register its private MCP URL in Multica only after independent authorization, a supported secure secret injection path, and test of the exact target runtime's network reachability.

## MCP verification

- `initialize` then `tools/list` (authenticated): eight tools.
- `github_get_deployments` for an exact SHA with no deployments returns HTTP 200 and `{"repo":...,"sha":...,"count":0,"deployments":[]}` — an empty list must not break the client schema.
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
