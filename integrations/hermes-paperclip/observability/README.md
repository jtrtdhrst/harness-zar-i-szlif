# Hermes → Opik: segmentation contract (GitOps candidate)

This change is **not yet a production deployment**. The running gateway uses a persistent `/opt/data` volume and loads 14 private copies of `plugins/opik/lifecycle.py`. Adding code to the image alone **does not** update those copies. Never claim completion from an image build alone.

## Trace dimensions

Retain project `hermes` as the authoritative Hermes-native trace project. Existing `paperclip-*` projects remain as Paperclip runtime sources; never mirror synthetic traces across projects to simulate correlated events.

For new Hermes-native traces from a profile-owned plugin copy, emit the existing provider/model/platform/turn/task metadata plus:

- `metadata.service=hermes-gateway`, `metadata.component=agent-turn`
- `metadata.agent_role=<verified role>`, `tags += agent:<role>`
- `metadata.memory_bank=hermes-<verified role>` (only the expected bank label; **not** proof of successful memory access)
- Existing LLM/tool spans remain under their original root trace.

A plugin loaded from `/opt/data/plugins/opik` (shared path), or an unfamiliar profile, emits no role label. Never infer agent identity from model name, prompt content, or historical trace names. Existing `task_id` is preserved; once the source-pinned per-run MCP bridge (PR #36) is accepted, it must carry the **real issued Paperclip UUID** as `paperclip:run:<uuid>`; a syntactically matching UUID is not E2E authentication evidence.

## Source verification and staging

```bash
python3 -m unittest discover -s integrations/hermes-paperclip/observability/tests -v
python3 integrations/hermes-paperclip/observability/apply_opik_segmentation.py --check /staged/plugin/lifecycle.py
python3 integrations/hermes-paperclip/observability/apply_opik_segmentation.py /staged/plugin/lifecycle.py
python3 -m py_compile /staged/plugin/lifecycle.py
```

The installer enforces SHA-256 `b029684c8c24703013126b90527f9b43ee7593c6acdd8afa8ffa13c442738a7a` on **each pristine** Hermes Opik plugin file. Reject drift. Staging/rollout must be implemented and reviewed as an atomic, reversible migration of the 14 persistent plugin copies, not an untracked live-volume edit. Preserve data and secrets.

## Acceptance gates

1. A reviewed, reproducible GitHub main SHA and Coolify image digest, with verified backup/rollback and actual 14-profile plugin readback.
2. Scoped positive CLI/API runs for all roles after startup, with each real trace carrying the correct agent tag and role metadata (and no cross-profile tags). No duplicate root traces or orphan spans.
3. An independent `hindsight_retain`/new-session `hindsight_recall` pair with the correct bank and a visible child tool span, plus explicit wrong-bank authorization denial.
4. One **real Paperclip-issued** run with the same run UUID in Paperclip and Opik Hermes root metadata, authorized scoped Wiki/Skills MCP child spans, unauthorized/expired grant denials, and independent CHO/CTO approval.
5. Verify Opik `read(trace)` for every positive flow, then read Coolify status, source SHA, image digest, health, and rollback. No bulk 14-agent cutover before gate 4.

**Opik 422 warning:** On 2026-11-04 the connected Opik `trace.update` operation rejected valid-looking tag-only updates with `traces[*].startTime must not be null`. Do **not** rewrite historical trace rows as a workaround. Use a separately reviewed SDK/backend fix or a validated update carrying the original start time, with readback, if historical labels are truly needed.

Scope is the instrumentation layer only; authorization remains in Paperclip and Hindsight. Do not log bearer credentials, tokens or prompts to derive identities.
