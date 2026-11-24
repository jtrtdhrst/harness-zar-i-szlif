# Multica ↔ Opik: verified telemetry and operator source

Production target: Żar i Szlif VPS, `/opt/operations/multica-opik/`. Source tracked here; authenticated Multica CLI exports only metadata. No prompt, tool argument, tool output, secret or credential is exported.

## Code and operational behavior

- `export.py` — run lifecycle to self-hosted Opik, source-native issue/run/agent ID and session linking, idempotent metadata patch with explicit project ID, independently read-back scores; recent-issue incremental scan.
- `value_metrics.py` — correctly distinguishes OpenCode Go quota-equivalent USD from actual billed charges. Computes known DeepSeek V4.1 Flash rates by weekday/time UTC, separate uncached input/output/cached reads, and rejects unknown models, missing usage, and cache-write pricing; cost absent rather than fabricated.
- `execution_hygiene.py` — objective tool-call pairing, from native `call_id` only; 27/27 live pair evidence. No content stored.
- `repair_plugin_profiles.py`, `fix_tool_span_types.py`, `fix_ttft.py` — private per-role plugin files, redacted tool typing, and removal of fake TTFT from total API duration in 14 role profiles.
- `multica-opik-export.service` — oneshot service invoked by existing systemd timer; last live run used `--max-items 40 --scan-window-days 3 --quality-items 10`. Missing scores are `unknown`, not fabricated. Full-scan backfill remains available when invoked without `--scan-window-days`.

## Distinct metrics

- `multica_run_completed`: 1 if native run ends completed, 0 if failed or cancelled; not test PASS, task correctness, production approval or release verification.
- `multica_tool_pairing_ratio`: matched native `tool_use`/`tool_result` by `call_id` divided by the maximum number of calls/results, only when a valid series is available; not result quality.
- `go_quota_usage_equivalent_usd`: estimate of OpenCode Go token quota usage from **published tariff**, not additional bill or actual provider invoice. Price source: https://docs.opencode.ai/docs/go/ (checked 2026-11-19). Approximate time tier uses UTC run start; API requests crossing a tier boundary are not individually priced.
- The source does **not** claim model success when an issue is still blocked or no independent GitHub CI/live/E2E evidence exists. Actual output-quality judge remains uncalibrated and content capture remains disabled.

## Live operator evidence — November 19, 2026

- `multica-opik-export.service`: `Result=success`, `ExecMainStatus=0`, timer active. With 3-day incremental scan, batch 40 + quality audit of 10 took 32.619 seconds vs 150-second systemd limit.
- A real native MCP Engineer run, `ZARI-33 / 01a1f496-a86d-717b-a2ca-0f8d40f760b4`: metadata contains `sdk_thread_id`, token/cache usage and model. Opik read-back shows `go_quota_usage_equivalent_usd=0.01357153`, `multica_run_completed=1` (off-peak).
- Opik actual SDK trace `01a1f497-90ef-722d-acc8-89f5e86f8081`: 41 spans, including 23 tool and 15 LLM.
- `multica_tool_pairing_ratio` automatically populated across recent run traces: ZARI-223 26/26, ZARI-261 7/7, ZARI-213 11/11, ZARI-240 12/12; independent readback via Opik MCP.
- Rollback copies in `/opt/operations/multica-opik/backups/`. `python3 -m py_compile`, execution_hygiene and value_metrics pure tests passed on host.

## SECURITY HOLD and native-agent Opik MCP

**ZARI-213 is still blocked**; this draft PR must not be self-merged. The direct workspace `opik` MCP was discovered and temporarily bound to MCP Engineer; its external endpoint `https://mcp-opik.kompaszbiorek.pl/mcp` returned HTTP 401 `invalid_token` because Cloudflare Access origin guard verifies signed JWTs limited to approved human identity. The failed agent binding was disabled; ChatGPT Opik connector's auth may not be copied to the agent.

To get a real authorized agent connection, use a **separately approved Cloudflare Service Auth policy** with a dedicated service principal and a pinned service identity at the origin. The current human-only guard must reject machine access until that new policy/identity is explicitly configured and independently reviewed. Do not bypass Cloudflare Access, disable the guard, share a human token or substitute an unauthenticated internal route.

Machine-to-machine auth docs: https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/ . The current operator's Cloudflare administration credentials are not accessible in the tools; no policy/credential was created.

## Regressions

Pure Python CI in `.github/workflows/opik-telemetry-ci.yml` compiles source and runs offline tests without any secrets. Native E2E release validation is independent and still requires explicitly approved deployment and privilege-scoped review.

Host-only readback: `python3 /opt/operations/multica-opik/export.py --profile zar --max-items 40 --scan-window-days 3 --quality-items 10 --dry-run`.
