# RepoWise GitHub sync

Host-side sync between the protected GitHub `main` branches and the RepoWise
workspace volume. RepoWise's `index_behind` compares the index with its mounted
checkout, so a stale checkout makes a stale index look healthy; the sync and the
freshness check below use the SHA fetched from GitHub instead.

## Install map

| Repo file | Host path |
| --- | --- |
| `ops/repowise/repowise_github_sync.sh` | `/opt/repowise-knowledge/sync-from-github.sh` |
| `ops/repowise/repowise_sync_gate.py` | `/opt/repowise-knowledge/repowise_sync_gate.py` |
| `ops/repowise/repowise_sync_index.py` | `/opt/repowise-knowledge/sync-index-replicas.py` |
| `ops/repowise/repowise_mcp_stage_smoke.py` | `/opt/repowise-knowledge/mcp-stage-smoke.py` |
| `ops/repowise/repowise_freshness_check.py` | `/opt/repowise-knowledge/repowise_freshness_check.py` |
| `ops/repowise/repowise_unwritten.py` | `/opt/repowise-knowledge/unwritten.py` |
| `ops/repowise/repowise_refill_pages.sh` | `/opt/repowise-knowledge/refill-pages.sh` |
| `ops/repowise/repowise_refill_all.sh` | `/opt/repowise-knowledge/refill-all.sh` |
| `ops/repowise/repowise_retire_orphan_flows.py` | `/opt/repowise-knowledge/repowise_retire_orphan_flows.py` |
| `ops/systemd/repowise-github-sync.{service,timer}` | `/etc/systemd/system/` |
| `ops/systemd/repowise-freshness-check.{service,timer}` | `/etc/systemd/system/` |

The host's existing `repowise-generate.service` executes `refill-all.sh`.
If modifying host scripts, update these canonical sources as well; redeploy
matching host files and keep a rollback copy before restarting any unit.

## Why the gate accepts `not_applicable`

`repowise_sync_gate.py` accepts `index_scope.upgrade.status` of `complete` or
`not_applicable` only when `git_tier` is `full`. `not_applicable` means the seed
is already full and no upgrade is needed; treating it as incomplete rejects
every sync after the first full index (`stage-seed-not-full`).

## Why the staged indexer uses `--index-only`

Without it the network-isolated stage tries LLM page generation, fails without
a key, and leaves `repositories.head_commit` and `.repowise-workspace.yaml` at
the old SHA.

## Why the page generator ignores one populated structural page

`onboarding:onboarding/active_landscape` is a deterministic page built from
git history and can have `model_name=''` while still containing complete
content. It is not an unfinished LLM page. The generator should reattempt it
only when its content is genuinely empty; otherwise a 30-minute timer makes
costly no-op model calls forever. Generation or reindex failures must propagate
a nonzero exit status instead of being reported as service success.

## Current source-of-truth boundary (2026-11-17)

RepoWise describes committed code, history, dependencies and documented
decisions; it does **not** prove runtime deployment or agent task execution.
Multica owns issue/run/handoff evidence. Hindsight stores verified execution
experience, not repository facts. The current Harness release admission is
`scripts/harness_release_admission.py` and
`scripts/harness_delivery_controller.py`, not the legacy
`paperclip-mcp/gitops/paperclip-mcp-auto-release.py`. See
`docs/architecture/HARNESS-RELEASE-MECHANICS-2026-11-17.md`.

## Verification

```bash
python3 -m unittest discover -s ops/repowise -p 'test_*.py'
REPOWISE_SYNC_STAGE_ONLY=1 /opt/repowise-knowledge/sync-from-github.sh
systemctl start repowise-github-sync.service
systemctl start repowise-freshness-check.service
systemctl start repowise-generate.service
docker exec repowise-mcp-lecwi3emh9hjxir7gphmalie sh -lc 'cd /workspace && repowise status --workspace --format json'
```

`repowise-freshness-check` fails when `github-main.json` is missing or older
than 30 minutes, or when either live checkout differs from the fetched SHA.
When the sync lock is held, its `ExecCondition` in `[Service]` skips the
check rather than reporting stale or misleading evidence.

## Operator-attested live resolution (2026-11-19)

> These operator readbacks supersede the earlier **at-audit** RW-mount
> warning below. It is a timestamped production observation, not a permanent
> guarantee for future releases.

**Evidence provenance and limits.** These production results were observed
directly by the authenticated human operator through the connected Ubuntu
SSH/Docker and local Coolify PostgreSQL read-only queries, plus RepoWise MCP
readback, on 2026-11-19 approximately 12:46–12:55 UTC. Sanitized command
results, timestamps, source SHA, image ID, unit results and test output were
reported in the **existing native Multica issue ZARI-240**, operator
evidence comment ID `01a1f3e1-a7c9-7534-9104-05871baba2d3`
(created 2026-11-19 12:56:54 UTC), and the adjacent operator E2E report
(12:57 UTC). CTO independently reviewed the exact source PR heads and CI,
**not** the production host or this separate runtime evidence. Thus the
claims below are operator-attested observations, not independent CTO
production acceptance; no secrets or credentials are reproduced.

- **Source merged to GitHub main:** PR #148 introduced explicit `:ro`
  Product/lock/token mounts and `:rw` episodes on the Coolify Compose
  resource; merge commit `778081695a4363167801e9a92779c0bf4fbf3eaa`.
  PR #147 merged the fail-closed publisher-discovery, identity, mount and
  source/rollback guards and regression tests; merge commit
  `bb514d9142c170c4f431878fafa7c45f1b3c657a`.
- **Operator-observed Coolify redeploy:** application `gl8bvfjtw2af8hkox4mguzzr`,
  deployment `fiyyjhphxbacloifhvr5ienw`, source commit `bb514d...`,
  database status `finished` at 2026-11-19 12:46:23 UTC; running container
  `publisher-gl8bvfjtw2af8hkox4mguzzr-20261119T124614`, image ID
  `sha256:82ee1357185ad7589345df5cbd15711cdc18c8e963706cf841770b01ae7a23ca`,
  Docker state `running/healthy`. Do not substitute the earlier manually
  recreated container as proof of this real Coolify redeploy.
- **Operator-read mount evidence:** Docker inspect and read-only filesystem
  checks verified `/workspace/product`, sync lock and token file are `RW=false`;
  `/workspace/product/.repowise/episodes` alone is `RW=true`.
- **Operator-read source-to-host parity:** canonical shell installed at
  `/opt/repowise-knowledge/sync-from-github.sh`, Git blob
  `0f35d191b7014aa91c402f0179f718005f592d88` matches the reviewed
  source from Harness main. Host prior-script backup:
  `/opt/repowise-knowledge/rollback/sync-script-pre-pr147-20261119T124931Z.sh`.
- **Operator-executed tests:** the entire RepoWise `ops/repowise/test_*.py` suite ran in the
  actual publisher image with MCP dependencies and returned **41/41 PASS**;
  new sync admission regression tests **14/14 PASS**, including changed
  labels, empty discovery, unexpected writable mounts, and no environment
  value collection. Host `bash -n` PASS.
- **Operator-read index and MCP:** controlled synchronization logged `PROMOTE_OK` and
  `SYNC_SUCCESS` at 12:49:15 UTC with Harness
  `bb514d9142c170c4f431878fafa7c45f1b3c657a` and Product
  `4feef6903dc21be5da0433a77b10549bf0009661`. The subsequently
  installed reviewed script detected the running Coolify publisher with
  its narrow field projection and passed identity/mount admission against
  the real container. `repowise-github-sync.service` and
  `repowise-freshness-check.service` returned success; RepoWise MCP
  `list_repos` reported the exact source SHA, and `get_context` retrieved
  this incident documentation. Anonymous publisher MCP requests returned
  401, as expected.
- **Scope:** These observations close the specific publisher/sync/mount
  regression. They do not by themselves mark the broader Multica
  ZARI-240 agent-to-production release workflow DONE, remove ZARI-213
  isolation HOLD, or establish every agent can publish a deployment
  observation. Role-scoped writer publication needs separate tool-use
  plus episode readback evidence.

## Confirmed Coolify publisher incident and source drift (2026-11-19)

- At 11:56:12 UTC the host's patched synchronizer included the Coolify
  publisher in the atomic stop/promote/rollback/restart transaction. At
  11:58:12 UTC it logged SYNC_SUCCESS for Harness SHA
  ec818fd755d146dfd0886e2a0fb07f8e1167461f and Product SHA
  4feef6903dc21be5da0433a77b10549bf0009661. Freshness check passed
  afterward. This dated runtime observation is not an ongoing guarantee.
- GitHub main's canonical repowise_github_sync.sh lacked the Coolify stanza
  despite the installed host script containing it. A normal redeployment
  could silently revert the fix. Keep host and canonical scripts identical.
- SECURITY GAP still present at audit: the running Coolify publisher mounts
  /workspace/product, the sync lock, and token file with RW=true even
  though tracked compose.publisher.coolify.yaml declares them read-only.
  Effective UID 999 can write to /workspace/product. This PR adds fail-closed
  source-side validation of exact Coolify identity and mount permissions:
  only /workspace/product/.repowise/episodes is allowed RW.
- DO NOT install the hardened sync script on the host until Coolify is
  redeployed/reconciled and Docker inspect shows the three read-only mounts
  and only episodes writable. Obtain independent exact-SHA review first.
- Controlled rollout: reconcile Coolify volumes, verify effective UID and
  mount flags, back up host script, install approved canonical version,
  run bash -n + unit tests, run one locked sync, inspect the
  SYNC_COOLIFY_PUBLISHER_INCLUDED / SYNC_SUCCESS / freshness-check markers
  and verify RepoWise MCP at the exact GitHub SHA. Roll back on failure.
- A chat observation or Multica issue comment is NOT automatically written
  into RepoWise. Technical lessons must be recorded in reviewed GitHub docs
  and ingested by GitHub sync; supported deployment episodes require a
  separate authorized writer and explicit readback.
