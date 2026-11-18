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

## Synchronization safety

Publisher writes hold the **same host advisory lock**
`/run/lock/repowise-github-sync.lock` used by
`repowise-github-sync.service`; no second indexer or scheduler.
The trusted service must mount that lock file with **read access** for its
dedicated identity, and set `DEPLOY_EVIDENCE_SYNC_LOCK` only if the approved
operator deliberately overrides the default. Linux flock permits an exclusive
advisory lock on a read-only descriptor. If the lock is held, missing, or
symlinked, the write fails closed with `sync_in_progress` or
`sync_lock_unavailable`, *before creating the EpisodeStore*. The lock is
released after the idempotent write/readback. Repository identities are exact
non-symlink directories; `.repowise` must not be a symlink.
The reader uses `sqlite3` `mode=ro` / `query_only=ON` and returns the
store's actual `observed_at_unix`, without triggering RepoWise's schema
creation or backfills.

14 focused tests include a racing lock holder, missing and symlink lock,
internal product-to-harness symlink, real MCP stdio, immutable record repeat,
and non-mutating reads.


### Full authenticated HTTP MCP fixture E2E — 18 November

An isolated `--network none` Docker fixture, with a disposable Git
repository and **non-secret test-only bearer**, successfully executed
the real protocol:

`initialize → tools/list → publish_deployment_observation →
get_deployment_observation → cross-repo denial`.

Both missing and incorrect bearers returned **401**; correct bearer
published a `SOURCE_ONLY_NOT_LIVE_VERIFIED` observation and retrieved
the exact source SHA. No production data was mounted, and the test
container and fixture were removed. The same flow is now repeated as
`test_real_http_mcp_tool_call_with_disposable_auth` in the automated
14-case regression suite.

Separately, the operator replayed the existing Product observation on
the **real RepoWise volume** through a disposable container with
source mounted read-only, the episodes sidecar separately writable,
the live root-owned sync lock mounted read-only and the fixed Git
safe.directory. It reported `created=false`, and the production
reader still retrieved the original episode. A separate disposable
Harness run while the host held that same sync lock exited nonzero
with `sync_in_progress`, before writing anything.

**GitHub source-transfer correction:** a previous remote tool truncated
both files at about 10 KiB. The files were subsequently reassembled
in bounded chunks and exact-comparison read back from GitHub at their
complete lengths (publisher 11,025 bytes, test suite 14,372 bytes
*as measured at the transfer*); the later code and tests match
the verified source snapshot. No claim is made that older green CI
on truncated files validated this implementation. Use the latest
exact-HEAD run instead.

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
