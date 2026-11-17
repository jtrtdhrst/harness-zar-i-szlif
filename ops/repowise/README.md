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
| `ops/systemd/repowise-github-sync.{service,timer}` | `/etc/systemd/system/` |
| `ops/systemd/repowise-freshness-check.{service,timer}` | `/etc/systemd/system/` |

## Why the gate accepts `not_applicable`

`repowise_sync_gate.py` accepts `index_scope.upgrade.status` of `complete` or
`not_applicable` only when `git_tier` is `full`. `not_applicable` means the seed
is already full and no upgrade is needed; treating it as incomplete rejects
every sync after the first full index (`stage-seed-not-full`).

The staged indexer runs with `--index-only`. Without it the network-isolated
stage tries LLM page generation, fails without a key, and leaves
`repositories.head_commit` and `.repowise-workspace.yaml` at the old SHA.

## Verification

```bash
python3 -m unittest discover -s ops/repowise -p 'test_*.py'
REPOWISE_SYNC_STAGE_ONLY=1 /opt/repowise-knowledge/sync-from-github.sh
systemctl start repowise-github-sync.service
systemctl start repowise-freshness-check.service
```

`repowise-freshness-check` fails when `github-main.json` is missing or older
than 30 minutes, or when either live checkout differs from the fetched SHA.
