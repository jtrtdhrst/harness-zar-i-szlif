# OpenCode → Opik: generation usage and provenance

## Incident — 2026-11-04
The production OpenCode Opik plugin emitted run-level traces and tool spans, but no LLM spans. The recorded example Opik trace 01a1a438-8709-7f84-9ba8-558c596173e5 (Paperclip run d83b8182-9fdc-473e-ac40-7deade3aafab) had 95 tool calls, llm_span_count=0 and missing cost details. Opik returned total_cost=0 despite large Paperclip input/cache usage. Existing tool spans were typed general, causing Opik tool-specific indicators to report incorrectly.

## Scope of fix
- Version-controlled copy of existing OpenCode plugin under observability/opencode-opik/index.mjs, retaining the original run-to-trace and tool flow.
- On completed OpenCode assistant message.updated events: emit one type=llm span, deduplicated by assistant message ID, with provider/model, run/agent/task correlation and separate fresh/cache-read/cache-write/output/reasoning usage.
- Classify existing tool.execute.after spans as type=tool rather than general.
- Never send message/prompt text or credentials in LLM spans. Keep attribution per Paperclip run and reuse the same root trace.
- Provider-reported USD is recorded as metadata only; no guarantee of actual billed cost. Token counters must not be multiplied by a single pricing rate.

## Verified source tests
Local node --check and node --test (mock Opik fetch) cover event deduplication, token accounting, zero prompt leakage, completed-only assistant messages, first-class tool spans and trace finalization. This is candidate source evidence, not a live production run.

## Release / rollback gate
1. Independent review by Harness Engineer / CHO, preserve existing native Paperclip review and source ownership.
2. Compare current production plugin SHA against the copied source baseline, resolve any drift by three-way merge; take a readback/backup of the original file. Do not touch Paperclip/OpenCode Core or agent model assignments.
3. Publish the reviewed exact candidate through the authorized managed config release path, not ad hoc edits to running containers.
4. Perform an actual task-bound Paperclip run; verify one or more Opik type=llm spans, model/provider/usage correctness, type=tool spans, and correct run ID. Verify redaction and repeated-event deduplication.
5. Measure fresh input, cache read/write, task success, latency and independently verifiable provider costs before/after. Roll back to backed-up SHA on regression.

Do not claim complete E2E based only on tests or PR state. Hermes native Opik segmentation PR #39 is separate and remains under its own review.

## Controlled release (source-pinned, no direct production patching)

The running OpenCode plugin is `/paperclip/.config/opencode/opik-observability/index.mjs` (inside the Paperclip container). On the Ubuntu host the same file is in the Paperclip Docker volume. `rollout.py` pins both the existing plugin hash and the reviewed candidate hash. The command `status` is read-only. `apply` and `rollback` require an explicit `--drained` admission assertion, independently verified no-live-run state, CHO/CTO review, and immutable source approval; **the flag does not itself check Paperclip run liveness**.

```sh
python3 observability/opencode-opik/rollout.py status --target /paperclip/.config/opencode/opik-observability/index.mjs
# Only after drain, approval, verified snapshot and candidate identity:
python3 observability/opencode-opik/rollout.py apply --drained --target /paperclip/.config/opencode/opik-observability/index.mjs
# Keep returned batch_id. If telemetry regression, drain again and rollback:
python3 observability/opencode-opik/rollout.py rollback --drained --target /paperclip/.config/opencode/opik-observability/index.mjs --batch-id <verified-batch-id>
```

Never run release commands on active production runs, never reuse a stale reviewed SHA, and never claim completion until a genuine Paperclip-issued issue run has a correlated Opik trace with first-class LLM/tool spans, safe metadata and cost provenance. The journal is private (0700), snapshots have checksums and reads are verified after apply and rollback. This PR alone does not migrate Hermes or alter the 14 Hermes profiles.
