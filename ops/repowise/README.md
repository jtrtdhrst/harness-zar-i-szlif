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
