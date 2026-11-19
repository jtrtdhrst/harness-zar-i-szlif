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
| `ops/systemd/repowise-github-sync.service.d/on-success-freshness.conf` | `/etc/systemd/system/repowise-github-sync.service.d/` |

The host's existing `repowise-generate.service` executes `refill-all.sh`.
Install `ops/systemd/repowise-generate.service.d/fast-freshness.conf` into
`/etc/systemd/system/repowise-generate.service.d/fast-freshness.conf`.
This serializes model writes against staged GitHub index promotion.
If modifying host scripts, update these canonical sources as well; redeploy
matching host files and keep a rollback copy before restarting any unit.

## Automatic freshness (2026-11-18)

GitHub App polling is used here rather than a public webhook.
The two private protected `main` branches are checked every 2 minutes
by `repowise-github-sync.timer`. Staged index promotion still requires
GitHub SHA verification, replica consistency, and an MCP smoke test.

The systemd `OnSuccess=` drop-in also runs the existing freshness checker
immediately after an **entire sync service succeeds**, avoiding a lingering failed
freshness unit after a moving-`main` staging retry. It does not run on a failed
sync, override a stale-SHA result, or replace the periodic timer. After
installation, run `systemctl daemon-reload`, verify
`systemctl show repowise-github-sync.service -p OnSuccess` and confirm a
freshness service exit 0 with `errors: []`. Roll back by removing **only** the
drop-in and reloading systemd.

`repowise-freshness-check.timer` runs every 3 minutes and flags
a last GitHub fetch older than 600 seconds or an out-of-sync checkout.
The existing `repowise-generate.timer` runs every 30 minutes;
its script now handles both unwritten and stale model pages and refreshes
the semantic vectors only after actual writes.

Repowise onboarding pages can remain marked `stale` after regeneration.
To avoid repeated, unnecessary model charges, pages updated after their
repo's indexed revision are not regenerated again for that same index.
A later GitHub commit causes them to be eligible again.

These intervals describe detection cadence, not a fixed E2E SLA.
RepoWise describes committed code; Multica/Coolify own evidence for
runtime deployment and agent execution.
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
than 10 minutes, or when either live checkout differs from the fetched SHA.
When the sync lock is held, its `ExecCondition` in `[Service]` skips the
check rather than reporting stale or misleading evidence.
