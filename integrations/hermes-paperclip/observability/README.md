# Hermes → Opik: segmentation contract (GitOps candidate)

This change is **not yet a production deployment**. The running gateway uses a persistent `/opt/data` volume and loads 14 private copies of `plugins/opik/lifecycle.py`. Adding code to the image alone **does not** update those copies. Never claim completion from an image build alone.

## Trace dimensions

Retain project `hermes` as the authoritative Hermes-native trace project. Existing `paperclip-*` projects remain as Paperclip runtime sources; never mirror synthetic traces across projects to simulate correlated events.

For new Hermes-native traces from a profile-owned plugin copy, emit the existing provider/model/platform/turn/task metadata plus:

- `metadata.service=hermes-gateway`, `metadata.component=agent-turn`
- `metadata.agent_role=<verified role>`, `tags += agent:<role>`
- `metadata.memory_bank=hermes-<verified role>` (only the expected bank label; **not** proof of successful memory access)
- Existing LLM/tool spans remain under their original root trace.

A plugin loaded from `/opt/data/plugins/opik` (shared path), or an unfamiliar profile, emits no role label. Never infer agent identity from model name, prompt content, or historical trace names. Existing `task_id` is preserved, and `thread_id` uses that same `paperclip:run:<uuid>` only for Hermes turns where the gateway supplies a Paperclip-formatted task ID; ordinary CLI sessions retain their previous thread IDs. Malformed Paperclip-formatted run IDs are rejected for thread correlation and retain their original session thread. This field is correlation only, never authentication evidence. Once the source-pinned per-run MCP bridge (PR #36) is accepted, it must carry the **real issued Paperclip UUID** as `paperclip:run:<uuid>`; a syntactically matching UUID is not E2E authentication evidence.

## Source verification and staging

```bash
python3 -m unittest discover -s integrations/hermes-paperclip/observability/tests -v
python3 integrations/hermes-paperclip/observability/apply_opik_segmentation.py --check /staged/plugin/lifecycle.py
python3 integrations/hermes-paperclip/observability/apply_opik_segmentation.py /staged/plugin/lifecycle.py
python3 -m py_compile /staged/plugin/lifecycle.py
```

The installer enforces SHA-256 `b029684c8c24703013126b90527f9b43ee7593c6acdd8afa8ffa13c442738a7a` on **each pristine** Hermes Opik plugin file. Reject drift. Staging/rollout must be implemented and reviewed as an atomic, reversible migration of the 14 persistent plugin copies, not an untracked live-volume edit. Preserve data and secrets.

## Reversible 14-profile deployment (after CHO/CTO review)

The reviewed release runner must execute these **source-controlled commands** against the persistent volume mounted at `/opt/data`, preferably inside an image-pinned, drained deployment transaction. Merely building the Dockerfile does not rewrite existing persistent profile plugin copies. `status` is read-only; `apply` writes all 14 profile-owned copies; `rollback` restores them from a checksum-verified journal. Each change retains original UID, GID and mode.

```bash
python3 integrations/hermes-paperclip/observability/rollout.py status --root /opt/data
# Stop admitting Hermes API runs, snapshot the volume, and verify rollback path.
python3 integrations/hermes-paperclip/observability/rollout.py apply --root /opt/data
python3 integrations/hermes-paperclip/observability/rollout.py status --root /opt/data
# Restart via Git-backed Coolify release using the reviewed exact SHA, not inline Dockerfile.
# If canary or role/trace readback fails:
python3 integrations/hermes-paperclip/observability/rollout.py rollback --root /opt/data --batch-id <id-from-apply>
```

Expected source SHA-256: `b029684c8c24703013126b90527f9b43ee7593c6acdd8afa8ffa13c442738a7a`; exact patched SHA-256 with Paperclip thread correlation: `15f38d6388d600ea888eff798ae9804df13c4d68515ff66c2a656a2b9a173768`. Drifts, partial updates, symlinks and corrupted backups are rejected before applying further changes. Atomicity is per-file; traffic must be drained while performing the fleet change. The journal remains after rollback as audit evidence.

The 10 regression tests and actual-profile-source dry deployment/rollback succeeded on the Ubuntu host 2026-11-04. **These are isolated staging tests and do not prove ingestion from live Hermes.** After controlled restart, verify all 14 actual `hermes` project traces have the right agent tag, bank label and native tool spans. Require PR #36's real authenticated Paperclip issue-run evidence before any agent cutover.

## Acceptance gates

1. A reviewed, reproducible GitHub main SHA and Coolify image digest, with verified backup/rollback and actual 14-profile plugin readback.
2. Scoped positive CLI/API runs for all roles after startup, with each real trace carrying the correct agent tag and role metadata (and no cross-profile tags). No duplicate root traces or orphan spans.
3. An independent `hindsight_retain`/new-session `hindsight_recall` pair with the correct bank and a visible child tool span, plus explicit wrong-bank authorization denial.
4. One **real Paperclip-issued** run with the same run UUID in Paperclip and Opik Hermes root metadata, authorized scoped Wiki/Skills MCP child spans, unauthorized/expired grant denials, and independent CHO/CTO approval.
5. Verify Opik `read(trace)` for every positive flow, then read Coolify status, source SHA, image digest, health, and rollback. No bulk 14-agent cutover before gate 4.

**Opik 422 warning:** On 2026-11-04 the connected Opik `trace.update` operation rejected valid-looking tag-only updates with `traces[*].startTime must not be null`. Do **not** rewrite historical trace rows as a workaround. Use a separately reviewed SDK/backend fix or a validated update carrying the original start time, with readback, if historical labels are truly needed.

Scope is the instrumentation layer only; authorization remains in Paperclip and Hindsight. Do not log bearer credentials, tokens or prompts to derive identities.
