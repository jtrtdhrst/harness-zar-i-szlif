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

## Native Multica publisher tool-use — 2026-11-19

This section supersedes the earlier pre-binding checklist for the **single
already-authorized Product writer**. It is not proof of wider agent deployment
authority, a production release gate, or per-role model credential isolation.

- **Real native run:** COO agent task
  `01a1f405-6f8f-7276-ba2c-ab33951f0361` on existing issue `ZARI-240`;
  trigger comment `01a1f405-6f66-7da8-b0b2-a8b443e965f4`. Actual native
  `tool_use`/`tool_result` records are in that run (sequences 65/66, 70/71);
  they used the pre-enabled `repowise-deployment-product` binding and did
  not require a new MCP server or credential grant.
- **Read negative:** Product episode ID `0000000000000000` returned
  `found=false`. **Write:** `publish_deployment_observation` returned
  `stored=true, created=true`, immutable episode `3ebdc8488ecdfc76` with
  `PARTIAL_LIVE_OBSERVED`, source SHA
  `4feef6903dc21be5da0433a77b10549bf0009661`, issue `ZARI-240`,
  deployment `npedmph1mo14h8b6rgpr9pg1`. The deployment UUID is from
  the **Product mascot-worker** Coolify resource; it is not evidence
  identifying the panel's deployment.
- **Native readback:** `get_deployment_observation(product,
  3ebdc8488ecdfc76)` returned `found=true` with matching source SHA,
  issue and deployment ID. This claim is based on the COO native MCP
  tool result only; no separate host SQLite or post-sync durability
  verification is attributed to that agent run.
- **Bounded evidence only:** the writer checked the public Product
  release SHA and `healthz=200`; it explicitly retains
  `immutable_digest=NOT_VERIFIED`, independent authenticated QA
  `NOT_RUN`, and rollback `NOT_RUN`. Do not convert the partial episode
  into an automatic Multica Done or a full delivery PASS. COO's
  GitHub/Coolify MCP bindings were still disabled at this readback.

**Separate unresolved native isolation failure** — CHO task run
`01a1f40a-ca05-71a1-bea5-86ceeda8fe9b`, existing `ZARI-213`,
performed a no-content file-descriptor probe: own role open allowed,
foreign CTO profile and shared repository cache denied (`EACCES`),
but global Hermes `auth.json` and `.env` **both opened successfully**.
No secret content was read. This is a confirmed shared-credential access
gap; keep ZARI-213 HOLD and do not enable broad agent permissions or
release status transitions. A genuine role-scoped credential broker
with two-role native positive/negative tests is still required; merely
copying shared credentials into per-role files does not make their
identities independent.

## Rollback

Historical pre-deployment note (2026-11-18): the module was additive, and
was not then installed as an auto-start service or bound to agents. As of
2026-11-19 a Product writer instance is running and scoped to COO, with the
bounded native observation/readback recorded above. This does not authorize
other roles or a release-grade write. Revert this feature branch/PR without changing existing
RepoWise MCP. Do not delete archived deployment episodes without a
separate audited retention decision. Never touch other repos or global
agent permissions.
