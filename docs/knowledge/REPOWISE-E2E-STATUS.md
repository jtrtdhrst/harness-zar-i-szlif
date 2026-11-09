# RepoWise backend-documentation acceptance log — 2026-11-09

## Verified documentation publication / indexing E2E

- Canonical backend reference: `docs/architecture/BACKEND-ARCHITECTURE-2026-11-09.md` (731 source lines, 16 chapters), merged in private harness PR [#85](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/85), commit `ed34c60c4db58ca11b8cc33fe1d607772a87e552`. Both executed CI workflows passed.
- Native agent lookup contract: `docs/knowledge/AGENT-LOOKUP.md`, merged in PR [#86](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/86), commit `ab068017e5bf2dab022ee9ed928bb89fed83a32c`. Both executed CI workflows passed.
- RepoWise v0.60.1 service `repowise-mcp-lecwi3emh9hjxir7gphmalie` reported Docker `healthy`. The native workspace now indexed harness exactly at `ab068017e5bf2dab022ee9ed928bb89fed83a32c` and product at `81c4b068b89f4c035098c6c9107f755f56919a87`; both `indexed=true`, `stale=false`, `commits_behind=0` at verification.
- Direct external RepoWise MCP: `list_repos` returned both repo aliases and exact SHA; `search_codebase(repo="harness",mode="path",query="BACKEND-ARCHITECTURE-2026-11-09.md")` resolved the canonical file; `get_symbol` returned exact verified source for lines 611–633; `get_symbol` returned exact updated lookup instructions for lines 8–16.
- Private GitHub App synchronization: existing native `/opt/repowise-knowledge/sync-from-github.sh`, systemd `repowise-github-sync.service` and `repowise-github-sync.timer` used unchanged. Service runs performed fetch → exact Git main SHA → `repowise update --workspace --index-only` → MCP restart; log reported `SYNC_INDEX_UPDATED_AND_MCP_RESTARTED` and `SYNC_SUCCESS`. Repeat service invocation reported both repos `SYNC_CURRENT` and `SYNC_SUCCESS` (idempotence).
- Timer was found disabled and re-enabled via `systemctl enable --now repowise-github-sync.timer`; at readback: `enabled`, `active`, 15-minute `OnUnitActiveSec`. The **unattended** future scheduled tick was not observed during this execution; the service itself and schedule activation were verified.
- Hermes Gateway configured 14/14 existing operational profiles with a native RepoWise MCP entry, api_server toolset and per-profile dotenv key presence. Gateway and RepoWise containers were `healthy`. This is **configuration verification**; no successful model-driven Hermes/Multica tool execution is claimed.

## Boundaries and outstanding evidence (not DONE for end-to-end AI-answer generation)

- `get_answer`: `degraded=no-llm-provider`; answer synthesis is unavailable. `REPOWISE_EMBEDDER=mock` disables semantic retrieval. Exact path lookup and verified source ranges are supported; concept search cannot be treated as reliable question answering.
- Cross-repo dependency graph remains partial; generic routes such as `GET /health` are false-positive candidates. Do not infer runtime connectivity from graph links or an architectural score.
- Native Hermes/Multica authenticated run → RepoWise query → agent response → telemetry (Opik) has not been proven. A direct container-token-based probe was blocked by tool safety controls and was not counted as success.
- No product application release was triggered or changed by these documentation-only PRs. Live product API/worker readiness and full business-domain E2E are separate gates; the dated architecture report labels their uncertainties.
- Existing Paperclip Wiki pages remain **historical** provenance, not active Multica role policy. Do not copy bearer credentials, private user data or complete agent transcripts into indexed docs.

**Verdict:** backend **documentation publication → GitHub main → private RepoWise sync/index → MCP exact path lookup and source readback: PASS**. Automatic timer enabled and service behavior verified; native Hermes/Multica run and model/semantic natural-language answers remain **NOT VERIFIED**.

