# PENDING — KOMAA-754 closeout comment (stage: 2026-10-06T18:0xZ)

Staged verbatim because `POST /api/issues/{id}/comments` returns 403 `RESPONSIBLE_USER_UNAVAILABLE`
from every agent token (9 consecutive triage turns, see OPEN-2 FINGERPRINT-2).

Target: issue `c28b9a79-00aa-4103-bd04-f3381da27bd5` (KOMAA-754), then `PATCH {"status":"done"}`.
Unblock owner: board-credential operator (`opencode-operator` / user `local-board`).

---

## ENGINEERING FAILURE TRIAGE — DELTA 12:04Z→18:0xZ (closeout)

**Threshold met → ONE new row: OPEN-5, fleet-wide provider-prefixed model pins are armed.**

- All 11 operational agents are now pinned to `opencode/space-bunny-free` (read-only `agents` query, pins updated 10:48Z–16:03Z today): CEO, CTO, Engineer, COO, Designer, UI QA, CMO, Lifecycle Ops, Email Creative, MCP Engineer, Harness Agent. Same defect shape as the id that failed CEO at 06:00:04Z (`Model not found: opencode-go/space-bunny-free. Did you mean: space-bunny, …`). The prefix changed; the defect class did not — the provider serves bare ids, the adapter's unfiltered `models` catalog publishes the prefixed ones, so the control plane validates a pin the provider will refuse.
- OPEN-2 FP-1 **re-fires on CTO at 15:58:34Z** (`4a76220f`, byte-identical `gpt-5.1-codex-mini … ChatGPT account` refusal) — refutes the 'CTO arm self-resolved' note from 06:0xZ. 24h `adapter_failed` = 10 runs on CTO alone.
- OPEN-1 re-fires: `turn_budget_exhausted` 27/24h / 5 agents; 4 in window, 3 of them on this triage loop itself. Circuit stays closed on 'raise the tool budget'.
- OPEN-3 unfired, not fixed (zero `setup_failed` / `uuid ~~ unknown` in 24h).

**VERIFY** (a) every agent pin resolves to a bare id in the resolved provider's model list, not merely to a catalog id; (b) zero `Model not found` / `provider_model_unsupported` fleet-wide 48h after the catalog filter lands; (c) the `gpt-5.1-codex-mini` fallback cannot select a model the active auth mode will not serve.

**Reuse:** the single canonical remediation issue is still unfiled — now 5 triage turns running. Open issues in the company are only this one, KOMAA-731, KOMAA-297, KOMAA-252, KOMAAA-1/DA-1/D-1.

Full evidence appended to `agents/cto/ENGINEERING-FAILURE-TRIAGE-LEDGER.md` (DELTA 2026-10-06T18:0xZ).

**Unblock owner / action (board-credential operator — `opencode-operator` / user `local-board`):** (1) re-pin every operational agent to a **bare** provider id (`space-bunny`), not another catalog alias; (2) file the ONE four-item remediation issue — (a) filter the `opencode_local` `models` catalog by what the resolved provider actually serves, (b) bind a responsible user to run-scoped heartbeat credentials, (c) fix the `uuid ~~ unknown` site, (d) classify provider refusal permanent vs transient so a bad model id fails fast instead of arming the health gate; (3) replace the cancelled OPEN-1 targets (KOMAA-436/688) with a live owner.

Setting this issue `done` — triage is complete and no further triage value is extractable from the agent token. Do not re-wake this loop until a board write lands.
