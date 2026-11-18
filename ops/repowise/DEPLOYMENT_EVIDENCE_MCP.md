# RepoWise deployment evidence MCP (ZARI-240)

## Purpose and trust boundary

This is a dedicated **write + read** MCP surface for dated deployment
observations in RepoWise's native `.repowise/episodes/episodes.db` store.
It does not alter GitHub refs, Coolify resources, services, user data, or
RepoWise-generated wiki pages. It is not an approval system.

Source: `ops/repowise/deployment_evidence_mcp.py`.
Test: `ops/repowise/test_deployment_evidence_mcp.py`.
The existing RepoWise GitHub sync remains the sole index synchronizer.

## Tools

- `publish_deployment_observation(repo, source_sha, issue, deployment_id)`:
  validate a fixed `harness`/`product` RepoWise checkout and Git object.
  For Product, independently read the pinned HTTPS
  `https://panel.zariszlif.pl/__release.json` source marker and
  `https://panel.zariszlif.pl/healthz`; deny mismatched/failed responses.
  Persist an idempotent `git`-tier `deployment_observation` episode with
  stable episode ID and immediately read back exact bytes.
- `get_deployment_observation(repo, episode_id)`: return only an episode
  of `deployment_observation` kind in that same allowed repository.

**Statuses are deliberately conservative.** Product is
`PARTIAL_LIVE_OBSERVED` at most. Harness without an independent live target
is `SOURCE_ONLY_NOT_LIVE_VERIFIED`. Immutable digest, independent
authenticated positive/negative QA and rollback remain
`NOT_VERIFIED`/`NOT_RUN`. The caller may not submit its own PASS flag or
arbitrary URL, filesystem path or shell command. An episode is evidence of
the observations listed, never full deployment acceptance.

`deployment_id` is a caller-supplied reference, **not authenticated Coolify
provenance**. Use `unknown` instead of inventing a deployment UUID.

## Safe local test

Inside the existing authorized RepoWise image with a mounted disposable
workspace, run:

```sh
python ops/repowise/test_deployment_evidence_mcp.py
```

MCP uses **stdio**, not a public HTTP listener. Every deployed MCP
instance MUST be assigned exactly one server-side repository scope:
`DEPLOY_EVIDENCE_ALLOWED_REPO=product` or
`DEPLOY_EVIDENCE_ALLOWED_REPO=harness`. With no scope or the wrong scope,
both tools fail closed. The repository is not selected by trusting agent
arguments alone.

```sh
DEPLOY_EVIDENCE_ALLOWED_REPO=product python ops/repowise/deployment_evidence_mcp.py
```

The MCP SDK stdio client must explicitly pass `DEPLOY_EVIDENCE_ALLOWED_REPO` in `StdioServerParameters.env`; relying on ordinary parent-process environment inheritance does **not** propagate that nonstandard variable. This is covered by a real stdio initialize/tools/readback/scope test.

The runnable host prototype is at
`/opt/repowise-knowledge/deployment_evidence_mcp.py`.
A controlled operator test on 2026-11-18 submitted Product source
`4feef6903dc21be5da0433a77b10549bf0009661`, issue `ZARI-240`,
reference `unknown` and read back episode `e6796ebc9b2af07f`.
The public health check was HTTP 200 and the live source marker matched.
The live episode survived a subsequent successful existing
`repowise-github-sync.service` run. Source of the event is a trusted host
operator invocation, **not a Multica agent run**.

## Optional private HTTP transport — operator-only staging

`--http` binds on `127.0.0.1:7339`, checks a mode-0600 regular
token file configured by `DEPLOY_EVIDENCE_TOKEN_FILE`, and requires
a **server-enforced** `DEPLOY_EVIDENCE_ALLOWED_REPO` scope. It
fails closed on missing, weak, world-readable tokens and on binding
to `0.0.0.0`. Never print the token or put it in an agent prompt.

2026-11-18 staging evidence: the disposable container was run with
`--network none`, so no external or production agent was exposed.
Requests with no token and invalid token were both **401**. A
request with the correct bearer passed authentication and received
**406** (it lacked required MCP content negotiation). A full
authenticated HTTP tools/call was **NOT_RUN** because the execution
environment blocked that credential-bearing test. Staging container
was removed; no HTTP service was promoted to production.

## Before binding to Multica agents / production

1. Retain ZARI-213 HOLD: do not grant cross-project checkout or GitHub
   write permissions to agents, run arbitrary stdio subprocesses, expose
   an unauthenticated network MCP endpoint or modify existing read-only
   RepoWise MCP without review.
2. Obtain independent exact-SHA CTO review of this branch, approve a
   scoped installation and secure authenticated MCP transport. Ensure
   each agent's bound tool can target *only its permitted repository* and
   the published tool identity is verified server-side, not by a user
   argument.
3. Serialize writes with existing RepoWise sync promotion lock (not a
   second indexer), then execute one real native authorized agent
   `tool_use` and `tool_result`; verify episode through the native
   RepoWise API/MCP after sync. Test stale marker, wrong repo, forged
   SHA, tenant isolation and no writes on denial.
4. For **full delivery PASS**, also independently collect real Coolify
   deployment UUID, immutable image digest, trusted CI, UI QA positive
   and negative authenticated E2E, and rollback. Those are intentionally
   outside this observation-only publisher until each has an
   independently verifiable source. Never mark a delivery issue Done on
   this tool's PARTIAL result.

## Rollback

The module is additive, not yet installed as an auto-start service and not
bound to any agent. Revert this feature branch/PR without changing existing
RepoWise MCP. Do not delete archived deployment episodes without a
separate audited retention decision. Never touch other repos or global
agent permissions.
