# Opik / Multica: tracked operator source

Private, verified-on-host source for production scripts installed at `/opt/operations/multica-opik/` on Żar i Szlif.

## Components

- `export.py` — fail-closed, metadata-only Multica lifecycle exporter to self-hosted Opik. Adds `sdk_thread_id` derived strictly from authenticated native run `result.session_id`, preserves issue-level grouping, and exports cache-read/cache-write token counts and verified model identifiers.
- `repair_plugin_profiles.py` — replaces shared profile plugin symlinks with isolated per-role copies.
- `fix_tool_span_types.py` — ensures Opik classifies `execute_tool` correctly, with tool arguments redacted when content capture is disabled.
- `fix_ttft.py` — corrects false TTFT reporting. Wall-clock API duration is NOT time-to-first-token; when no real provider-measured TTFT is present, the metric is absent, not fabricated.

## Evidence, 19 November 2026

- 14/14 role-local Hermes plugin copies verified.
- Production native agent trace: `01a1f497-90ef-722d-acc8-89f5e86f8081` in the existing private Opik project `multica-zar-i-szlif`. 41 spans, including 23 typed tool and 15 LLM.
- Metadata lifecycle trace `01a1f496-a86d-717b-a2ca-0f8d40f760b4` has matching SDK thread ID, issue/run/agent IDs, model, cache usage, attempt and status; confirmed by Opik readback.
- `multica-opik-export.service` is `Result=success`, `ExecMainStatus=0` after project-context PATCH fix, timer active.
- Live backups retained under `/opt/operations/multica-opik/backups/`; no model prompts, response text, tool arguments or access tokens exported.

## Security and release gating

**Security HOLD ZARI-213 remains unchanged.** This branch documents the exact currently installed hotfix; it does NOT itself authorize a deploy/merge or guarantee the next image contains it. Independent review, tests and exact SHA reconciliation remain required.

Existing workspace Opik MCP endpoint `https://mcp-opik.kompaszbiorek.pl/mcp` rejects the Multica agent with HTTP 401 `invalid_token`. The external access guard verifies Cloudflare Access signed JWTs for an approved human identity. **Do not disable/bypass the guard or copy a human token to an agent.** Agent-native Opik MCP reading requires an approved delegated identity or explicitly scoped read-only service principal before rollout.

Actual billable unit rates for `openai-codex:gpt-6-luna` and `opencode-go:deepseek-v4.1-flash` were not independently verified. An absent cost must remain unknown, never guessed as USD 0. Do not assume the TTFT metric is available for non-streaming provider responses.

## Regression commands (run on authorized host only)

```sh
python3 -m py_compile ops/observability/opik/*.py
python3 ops/observability/opik/export.py --profile zar --max-items 1 --dry-run
python3 ops/observability/opik/fix_ttft.py  # validates installed profile hashes; do not use --apply without release review
```

Tracked files are host-specific. Keep service ownership/ACLs, rollback copies and workspace isolation intact.