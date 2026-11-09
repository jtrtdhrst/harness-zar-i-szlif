---
title: Agent execution, independent acceptance and blocked recovery — v61
type: policy
updated: 2026-10-20
---

# Żar i Szlif — agent execution & acceptance contract v61

## Authority: one owner, one canonical issue, real evidence
An issue has ONE accountable domain executor. Access/environment repair is a causal dependency, not a reason to steal the product issue or create a parallel coordination issue. Every material mutation is followed by an authoritative readback. Reporting done, launching a routine, filing a comment, or queuing an agent is not equivalent to a verified delivered artifact.

## Operational hierarchy and domain fit
| Executor | Owns | Escalation | Independent acceptance |
| --- | --- | --- | --- |
| CEO | Strategy, company governance, nondelegable approvals | Authorized user only when truly nondelegable | COO/appropriate independent reviewer when review is mandatory |
| COO | Routing, WIP, actionability, dependencies and dispatch | CEO policy; Harness technical access | Never domain-self-approves; routes to appropriate owner |
| CTO | Technical architecture, delegated delivery, security, reviewed releases and documentation disposition | COO/CEO for governance | Non-author competent reviewer when CTO authored candidate |
| CMO | Brand, marketing strategy, consent and email/lifecycle acceptance | COO | Independent COO/CEO when CMO authored candidate |
| Harness Agent | Paperclip/OpenCode core-adjacent environment, gateway, host, tools/plugin projection, runtime, access; sanctioned source-overlay fixes | COO → CTO for release/architecture | Independent CTO/competent technical non-author |
| Engineer | Application code, business logic, Supabase integration, APIs, code components | CTO | CTO (unless author); qualified independent technical fallback |
| MCP Engineer | PRODUCT MCP contracts, Qdrant/vector database, embeddings, retrieval/RAG and external integration synchronization | CTO | CTO (unless author); qualified independent technical fallback |
| Designer | Native editable Plasmic/UI composition and responsive design | CTO | UI QA + CTO technical as applicable |
| UI QA | Independent visual/accessibility and staging behavior verification, no implementation | CTO | CTO for final closure where required |
| Email Creative | Approved email creative, safe HTML, previews | CMO | CMO |
| Lifecycle Ops | Approved lifecycle and Mautic non-sending implementation/tests | CMO | CMO |

**Hard boundaries:** MCP Engineer does not own Paperclip/OpenCode MCP gateway, generic Git/CI control-plane, host or runtime repair. Harness does not absorb domain feature implementation. CTO may approve a technical release but **cannot provide the independent implementation review of its own candidate**. Org `reportsTo` alone is not a functioning reviewer stage.

## Evidence-bearing state machine
- `todo → in_progress`: only if canonical GetExecutionEligibility is executable=true, genuine scope/agent tool authorization, no active or queued duplicate run, and neither unresolved dependency nor execution hold.
- `in_progress → in_review`: only if immutable candidate or audited artifact exists, exact DoD/test evidence, `DOC_IMPACT=YES` + updated canonical wiki/hash or `NO` + explanation, a named domain-competent non-author reviewer is available, and the backend atomically persisted first-class reviewer actor/stage and created a real review wake. Never use generic anyone confirmation.
- `in_review → done`: only reviewer-authorized first-class PASS with independent checks, docs disposition and production readback when terminal acceptance requires release. A run/comment/manual `status=done` cannot bypass reviewer stage.
- `in_review → original executor`: CHANGES includes exact rejected SHA/requirements/failed tests; original executor preserved and one event-driven wake only after distinct causal input. Never 409 fallback to raw status PATCH.
- `in_progress → blocked`: structured causal reason, actual owner, stable fingerprint, explicit eligible next action and release condition. True relational dependency remains in DAG; environment/credential/tool blockage routes to existing Harness canonical root without reassigning domain owner. Blocked is not a parking place.
- `blocked → eligible`: Harness proves authenticated native provider access in original executor runtime, source owner/CTO accepts original issue gate, COO does fresh authoritative eligibility and wakes domain executor exactly once. No forced wake under safety hold.
- `unknown / inconsistent`: fail-closed, no speculative mutating repair or human-only questions.

## Operational controls
- **Backend, not prompts, must reject** missing named reviewer; self-review/creator review; actor mismatch; missing DoD/docs; duplicate same-fingerprint status/retry; raw blocked without causal owner; unauthorized privilege; and status PATCH skipping first-class decisions. Audit at both MCP and HTTP entry points.
- P0 source work: KOMAA-849/865 for atomic review/409; KOMAA-765 for routine dedup and metric semantics; KOMAA-874 for relational blocked graph; KOMAA-797/798/803 for native tools/authorized host.
- LIVE blocker evidence (2026-10-19): KOMAA-765, KOMAA-839, KOMAA-789 are wedged (`in_review`, named agent in stage, effective currentParticipant USER, zero live reviewer). They cannot be approved or demoted by prompt. Resolve the source bug first.
- A legitimate nondelegable privilege/consent/release gate remains untouched until authorized actor can approve it. Never create unnecessary Board/user technical diagnostics. No secret values in evidence.
- A skill, wiki or routine text edit is not proof the server enforces the policy. Acceptance = source tests (RED/GREEN) + independent exact-SHA review + safe release + public endpoint E2E readback.
- Use native MCP first; do not infer access from aggregate tools installed or a stored secret_ref. Tool check in issue runtime and safe readback are required.
- Managed MCP connections reach the agent runtime only through the single per-run `paperclip-assigned` gateway entry; per-connection tools are resolved server-side. `GetAgentEffectiveTools` and `VerifyAgentTool` enumerate Paperclip-native tools only, so a managed connection is absent from them BY DESIGN: treat a 0-match filter as a catalogue gap, never as proof of missing access. Per-principal access proof = gateway `tools/list` with the principal's own task-bound scoped token PLUS one real authenticated provider call. Connection `healthStatus: ok` covers transport only; a provider that cannot reach its backing store must not report healthy, so accept a connection on provider-level readback, never on the registry flag. Durable detail and the no-retry rule: [[wiki/concepts/context-first-execution]].

## Dispatcher cycle and metrics
One hourly COO routine, bounded two broad reads, max 8 selected candidates, max 2 unique safe wakes, no duplicated run while agent busy. A guarded event/activity policy is permitted only if it does not lose external recovery events, outstanding callbacks, approvals or overdue monitors; backend tests must prove positive/negative wake coverage. Current `require_external_activity` is a temporary no-op optimization, NOT a guaranteed condition watcher; externally changed facts without Paperclip activity may be missed. Add source tests before claiming autonomous unconditional recovery.

Measure four separate quantities: `adminRoutineRuns`, `newAgentRunning`, `acceptedCandidates`, and `acceptedLiveDeliveries`. Routine `completed` does not imply accepted product work. The routine metrics inconsistency (40 records with linkedIssueId but 40 counted as without) is recorded under KOMAA-765.

## Regression matrix (must be GREEN before declaring production-ready)
1. Engineer submits valid candidate -> independent CTO PASS -> docs hash readback -> done; CTO implementation cannot self-review.
2. Lifecycle Ops creative -> independent CMO verifies consent/token/send-OFF and docs -> PASS/CHANGES; same-SHA retries = 0.
3. Harness infra task cannot self-approve or enter orphan `in_review`.
4. Agent stage reviewer CTO but currentParticipant USER -> atomic validation fails closed, no forged user confirmation; source repair routes correct reviewer once.
5. 409 `no_longer_stalled` -> 0 PATCH/status/reviewer-wake.
6. Missing Plasmic/Supabase/Mautic native MCP -> existing Harness access root exactly once, domain issue retained, safe original-agent readback, then one resume.
7. Real relational dependency or manualOnly safety hold -> 0 force wakes/auto-unblocks.
8. External provider recovery with NO `activityLog` event -> event-monitor or explicit periodic preflight still detects it before SLA, no starvation.
9. 40 completed routine execution issues with zero product artifacts -> 0 accepted deliveries, no false orphan metrics.

## Language
Internal operations, issue discussions, reviews, test logs and routine reports use English. Preserve Polish product copy, brand Żar i Szlif, UI, lore, email subjects/preheaders/CTA and unsubscribe literals unchanged.

## Live configuration deployment notes — 2026-10-19
- Effective capability/role contract `CANONICAL GOVERNANCE v61` confirmed in CEO, COO, CTO, CMO, Harness, Engineer and UI QA agent records; other role-specific existing v57/v59 contracts retain their own boundaries. MCP Engineer direct manager is CTO and org chain verified healthy.
- UI QA skill materialization RECURRENT DEFECT: initially `kompas-ui-qa-specialist` desired but missing; SyncAgentSkills installed exact version 8efe93b3 and readback showed installed, BUT later Harness skill sync evicted it again. COO `paperclip-router` was also desired but missing. This is NOT durably repaired by per-agent resync: shared OpenCode/Claude skills home cross-agent eviction requires isolated runtime projection SOURCE fix in existing KOMAA-797 (negative concurrent sync tests).
- Single hourly COO routine `0bc53e5e-cbb4-4bd1-8bfa-65d7fa189790` policy updated to `activityGatePolicy=always` pending safe conditional gate source coverage (previous `require_external_activity` misses changes not logged in Paperclip); existing `0 * * * *` Europe/Warsaw, `coalesce_if_active`, `skip_missed` unchanged. No second hourly routine.
- Reassigned three weekly *operational* maintenance routines from strategy-only CEO to Harness, preserving cron/timezone and `require_external_activity`: agent improvement `d4679aed-4dcb-468f-9f9f-dc062e9c25da`, context compression `78abd1f7-ce84-4f59-bb0c-73805f05e76e`, skill lifecycle `68617aa7-e059-4bd5-821d-96d6b6f5a823`. All three specialist loop skills installed for Harness. These changes do not transfer company strategic policy authority or CTO release authority.
- SECURITY: `WEEKLY SKILL LIFECYCLE` prohibits real-agent skill test snapshots until KOMAA-839 secret leak is fixed with first-class independent acceptance and live public redaction; static audit only in interim. Last skill audit of router emitted warnings from archived pre-v52 reference files, not the operative `SKILL.md`.
- Read-only company reconciliation detected 14 findings, including valid blocked execution holds, diverged blockedBy projection, and terminal-with-hold artifacts. **No global apply** performed: valid holds or relational dependencies cannot be cleared simply to improve a metric. Open review wedges KOMAA-765/839/789 remain backend P0, not resolved by policy text.
- Routine v60 E2E previously tested with KOMAA-997 `done`/NO_ACTIONABLE_WORK; separate v61 manual-trigger attempt was not authorized by the tool surface, so do NOT claim a new E2E PASS until an actual v61 run is observed in routine history.


## 2026-10-19 v61.1 correction — shared skills runtime
A real negative cross-agent regression was observed AFTER the initial positive QA skill readback. Fix the shared home; do not claim durable UI QA/COO skill installation yet. Hourly routine revision 78 uses `DEGRADED_DELIVERY_ONLY`: still performs rigorously scoped native deliver_only on fully eligible issues, never unsafe review/blocked repairs or a privileged fallback; separately records KOMAA-797 tooling gate. Four current review wedges include KOMAA-765, KOMAA-839, KOMAA-789, KOMAA-1001; KOMAA-797 additionally has raw in_review without first-class review stage (a separate backend admission defect). Source root KOMAA-849 contains exact reproduction and tests. All current model reports must distinguish prompt/config repairs from LIVE backend enforcement.
