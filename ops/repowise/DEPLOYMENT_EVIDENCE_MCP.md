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

MCP uses **stdio**, not a public HTTP listener:

```sh
python ops/repowise/deployment_evidence_mcp.py
```

The runnable host prototype is at
`/opt/repowise-knowledge/deployment_evidence_mcp.py`.
A controlled operator test on 2026-11-18 submitted Product source
`4feef6903dc21be5da0433a77b10549bf0009661`, issue `ZARI-240`,
reference `unknown` and read back episode `e6796ebc9b2af07f`.
The public health check was HTTP 200 and the live source marker matched.
The live episode survived a subsequent successful existing
`repowise-github-sync.service` run. Source of the event is a trusted host
operator invocation, **not a Multica agent run**.

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
