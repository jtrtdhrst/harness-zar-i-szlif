# RepoWise backend-documentation acceptance log — 2026-11-09

## Verified documentation publication / indexing E2E

- Canonical backend reference: `docs/architecture/BACKEND-ARCHITECTURE-2026-11-09.md` (731 source lines, 16 chapters), merged in private harness PR [#85](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/85), commit `ed34c60c4db58ca11b8cc33fe1d607772a87e552`. Both executed CI workflows passed.
- Native agent lookup contract: `docs/knowledge/AGENT-LOOKUP.md`, merged in PR [#86](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/86), commit `ab068017e5bf2dab022ee9ed928bb89fed83a32c`. Both executed CI workflows passed.
- RepoWise v0.60.1 service `repowise-mcp-lecwi3emh9hjxir7gphmalie` reported Docker `healthy`. The native workspace now indexed harness exactly at `ab068017e5bf2dab022ee9ed928bb89fed83a32c` and product at `81c4b068b89f4c035098c6c9107f755f56919a87`; both `indexed=true`, `stale=false`, `commits_behind=0` at verification.
- Direct external RepoWise MCP: `list_repos` returned both repo aliases and exact SHA; `search_codebase(repo="harness",mode="path",query="BACKEND-ARCHITECTURE-2026-11-09.md")` resolved the canonical file; `get_symbol` returned exact verified source for lines 611–633; `get_symbol` returned exact updated lookup instructions for lines 8–16.
- Private GitHub App synchronization: existing native `/opt/repowise-knowledge/sync-from-github.sh`, systemd `repowise-github-sync.service` and `repowise-github-sync.timer` used unchanged. Service runs performed fetch → exact Git main SHA → `repowise update --workspace --index-only` → MCP restart; log reported `SYNC_INDEX_UPDATED_AND_MCP_RESTARTED` and `SYNC_SUCCESS`. Repeat service invocation reported both repos `SYNC_CURRENT` and `SYNC_SUCCESS` (idempotence).
- Timer was re-enabled after an additional unexplained stop; a **real unattended tick** ran at `2026-11-09T22:46:55Z`, fetched both private GitHub `main` refs, reported both `SYNC_CURRENT` and `SYNC_SUCCESS` at `22:46:58Z`. Timer readback: `enabled`, `active`, 15-minute `OnUnitActiveSec`. No claim that a privileged external actor cannot stop the timer again.
- Hermes Gateway configured 14/14 existing operational profiles with a native RepoWise MCP entry, api_server toolset and per-profile dotenv key presence. Gateway and RepoWise containers were `healthy`. This is **configuration verification**; no successful model-driven Hermes/Multica tool execution is claimed.

## Boundaries and outstanding evidence (not DONE for end-to-end AI-answer generation)

- `get_answer`: `degraded=no-llm-provider`; answer synthesis is unavailable. `REPOWISE_EMBEDDER=mock` disables semantic retrieval. Exact path lookup and verified source ranges are supported; concept search cannot be treated as reliable question answering.
- Cross-repo dependency graph remains partial; generic routes such as `GET /health` are false-positive candidates. Do not infer runtime connectivity from graph links or an architectural score.
- Native Hermes/Multica authenticated run → RepoWise query → agent response → telemetry (Opik) has not been proven. A direct container-token-based probe was blocked by tool safety controls and was not counted as success.
- No product application release was triggered or changed by these documentation-only PRs. Live product API/worker readiness and full business-domain E2E are separate gates; the dated architecture report labels their uncertainties.
- Existing Paperclip Wiki pages remain **historical** provenance, not active Multica role policy. Do not copy bearer credentials, private user data or complete agent transcripts into indexed docs.

**Verdict:** backend **documentation publication → GitHub main → private RepoWise sync/index → MCP exact path lookup and source readback: PASS**. Automatic timer enabled and service behavior verified; native Hermes/Multica run and model/semantic natural-language answers remain **NOT VERIFIED**.


## Additional execution readback — 2026-11-09, 22:53 UTC

- Native RepoWise workspace conformance configuration was applied in the persistent `.repowise-workspace.yaml` (backup: `/opt/repowise-knowledge/rollback/repowise-workspace-before-conformance-20261109.yaml`). Two deny rules: `product !-> harness::paperclip-mcp`, `product !-> harness::multica-mcp`. `repowise update --workspace --index-only` recomputed workspace analysis; `repowise workspace check --format json` and MCP `get_conformance` both returned `rules_evaluated=2, violations=0, cycles=0`. An isolated in-memory negative control against an existing graph edge yielded one violation as expected.
- RepoWise graph evidence remains `partial`, with 9/14 identified services isolated and several generic endpoint matches. Zero rule violations does not prove complete connectivity; do not equate graph score 9.9/10 with release readiness. See `docs/architecture/REPOWISE-CONFORMANCE-2026-11-09.md`.
- Host `/usr/local/bin/opencode` was an empty zero-byte stub; it was backed up and atomically replaced with a symlink to official native `opencode-ai@1.19.5` installed under `/opt/experiments/multica-poc/runtime/native-opencode`. `opencode --version` returned `1.19.5` and the binary was validated as Linux x86-64 ELF. No daemon, model selection or agent dispatch was changed by this installation.
- Hermes Gateway: exactly 14 canonical profiles parsed as YAML and each had native `mcp_servers.repowise.url=http://repowise-mcp:7338/mcp`; container-to-service DNS resolved and anonymous request returned HTTP 401. Hermes and RepoWise containers remained healthy. This is a configuration/connectivity/security-negative test, **not** an authenticated agent-run pass.
- Native Multica workspace `28378cc8-2c3a-4f8e-af1c-63e308407b17` (`zar-i-szlif`) had `0` agents, `0` runtimes and `0` workspace MCP library entries at readback. Existing systemd `multica-zar-daemon.service` is enabled but gated by absent `/srv/multica-zar/.multica/zar-prod-verified`; the native preflight `multica-zar-auth-verify` returned `AUTH_NOT_READY` and the CLI reported `not authenticated: run 'multica login' first`. Do not bypass this guard or claim a live Hermes→Multica→RepoWise E2E.
- Remaining user-managed inputs: RepoWise LLM provider and semantic embedder. Separate remaining integrations: an authorized Multica CLI login / runtime registration, agent provisioning, actual authenticated Hermes/Multica-to-RepoWise call and Opik trace. A new PAT should be entered through the native CLI interactive flow, **never** committed or passed in a shell argument.

## Final live remediation and measured agent value — 2026-11-09 23:59 UTC

**Root cause confirmed**: at 23:14:50 UTC a separate authorized `harness-ops` shell explicitly issued `systemctl stop repowise-github-sync.timer`; at 23:15:01 the previous staging full-indexer was killed by a **1 GiB cgroup OOM (exit 137)**. The host script subsequently used a 4 GiB no-swap indexer limit.

**Critical correctness bug**: the former live `product/.repowise/wiki.db` held both `harness` and `product` repository records. The original stage MCP smoke also incorrectly expected the harness-owned `scripts/product_native_promotion.py` file in `product`. The smoke was changed to a real product source file, and an explicit negative ownership assertion now fails on a harness-only path in product.

**Tested recovery pipeline**:

1. Isolated full upgrade: product generated 118 pages, harness 284 pages without OOM. Native workspace updater completed.
2. Offline staged positive/negative source isolation queries: PASS for both repos.
3. Staged authenticated MCP smoke: initialize/tool list, aliases, product search/context, harness search/context, negative isolation, and cross-repo blast radius all PASS.
4. Atomic promotion: `PROMOTE_OK`, backup at `/opt/repowise-knowledge/rollback/sync-20261109T235316Z-133837`.
5. Production readback: `LIVE_REPO_OK` on both SHAs, `LIVE_CURRENT`, `LIVE_STATUS_OK`, final `SYNC_SUCCESS` (exit 0). RepoWise MCP back to `healthy`; both isolated SQLite index DBs `pragma quick_check=ok`.
6. Independent external RepoWise MCP readback: harness-only file absent in product; product-only Worker present in product; `get_overview(repo="product")` now correct. `get_conformance`: 2 native checked rules, zero detected violations, **partial** architecture evidence.
7. Re-enabled 15-minute `repowise-github-sync.timer` read back `enabled` and `active`. An immediate independent service invocation returned `SYNC_CURRENT` on both repos without full rebuild, proving idempotence. Monitor subsequent unattended ticks before asserting ongoing unattended reliability.

The production product release remained `98cd058155dbf4c268777246fc510324f98f7dc5`, with `/healthz` HTTP 200. No product application deployment was made.

**Actual model measurements**: see `docs/knowledge/REPOWISE-AGENT-BENCHMARK-2026-11-09.md` (7 real OpenCode DeepSeek v4.1 Flash plan runs, 2 paired tasks, source-safety and post-fix regression, metadata-only private Opik project `repowise-agent-ab-20261109`). On a completed same-document pair, RepoWise answered in 39.7 s vs 57.3 s for GitHub (30.7% faster by recorded event time, 7 vs 10 tool calls), with a **mixed** token picture. No generalizable efficacy claim from this small sample.

**Still open (separate owners)**: the user is configuring RepoWise LLM/semantic embedder. Multica production `zar-prod` remained unauthenticated, and authenticated execution of 14 Hermes profiles → Multica → RepoWise → Opik has **not** passed E2E. Do not bypass native Multica login guard or claim 14/14 live role runs.
