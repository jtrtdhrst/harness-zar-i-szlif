# Harness Agent — Systemic Reliability v71 (20 Oct 2026)

Owner: Harness Agent; dispatch owner COO; independent release/review owner CTO. Language: English for technical operations, Polish for product copy. Keep Paperclip/OpenCode Core and privileged gates intact.

## Live baseline
- 200 Harness runs: succeeded 151, timed_out 18, cancelled 20, interrupted 2, failed 2, running 3, queued 4. Of 151 successful runs: 93 blocked, 41 completed, 15 advanced, 2 unknown. A successful routine is not accepted product output.
- Last-day 24 done Harness-assigned issues: 22 routine/watchdog tickets, 2 other (KOMAA-1052 and KOMAA-435). KOMAA-865 had 64 recorded recent executions without closing the deployment root. KOMAA-468 had repeated 1800s timeouts.
- Huge run context: observed 73,397 prompt characters, with substantial session handoff, and multimillion cached input tokens.

## Applied configuration and proof
| Test | Expected | Readback |
|---|---|---|
| C01 | maxConcurrentRuns=1 (was 3) | PASS |
| C02 | timeoutSec=1200 (was 1800) | PASS |
| C03 | heartbeat.enabled=false; assignment/automation enabled | PASS |
| C04 | harness-task-recovery v71 installed | PASS, version 74cb56fe-f9ff-4517-8424-5d970835e100 |
| C05 | engineering-failure-triage-loop v71 installed | PASS, version 40b1e314-b3e8-4880-83a7-a3baf3e20cda |
| C06 | routine hourly active, coalesce_if_active, skip_missed | PASS |
| C07 | skills audit | Triage PASS; Recovery WARNING (network_reference), not a hard stop |
| C08 | public MCP health/read, negative auth, idempotency, audit, manifest, artifact | SMOKE_PARTIAL_PASS: 0 failed, 2 skipped (active-issue comment write/read canary deliberately not executed) |
| C09 | original Harness scoped tool discoverability | PASS registered/authorized/reachable; generic probe only, E2E original runtime UNVERIFIED |
| C10 | live health and database backup | PASS during verification |
| C11 | source-enforced retry circuit and 1 writer across distinct agents | NOT VERIFIED; production enforcement required |
| C12 | original operation, negative auth, independent review, one eligible COO wake and accepted product | NOT VERIFIED |

## Active contracts
Agent capabilities v71: 8583 -> 3876 characters. Skill recovery 11430 -> 6347; triage 8321 -> 4969; routine 5396 -> 3585. Before each repair: canonical root + normalized fingerprint + original affected principal + eligibility + live writer. No duplicate retry absent changed causal input, no repeat 403/404/409/422/timeout, bounded 3 diagnostic reads and two small log tails, checkpoint by minute 18, one reversible mutation and readback, original failure reproduction, negative auth checks, exact candidate/live artifact and rollback, independent CTO review and one COO handoff. No generic human-only access cards for technical diagnostics; no self-grant, review-to-todo fallback or dirty workspace destruction.

## Remaining source-level execution blockers — DO NOT mark fixed
1. KOMAA-468: implement atomic workspace holder isolation at backend checkout/provisioning across DIFFERENT agents, replay concurrency and negative inheritance tests. Config maxConcurrentRuns=1 is only a prospective per-agent safety limit, not the root fix.
2. KOMAA-849/KOMAA-865: reviewed fail-closed atomic named-reviewer admission, safe 409 handling, public live test, rollback and exact SHA. Do not deploy while hold/governance gate active.
3. Repeated timeout/403/409: add backend fingerprint circuit latch so scheduler refuses unchanged retry; agent instructions alone cannot enforce it at claim time. Test one causal delta => one eligible wake.
4. Prompt/session handoff generator: bound byte size, filter old duplicated comments and skills, checkpoint persisted separately, redact secrets. Verify genuine new wake still contains sufficient current context.
5. Measure next 24h unique technical roots repaired and accepted product outputs, timeouts, duplicate normalized fingerprints, aggregate tokens per ACCEPTED fix. Never claim improvement based only on run success, routine completion or this document.

Exit / rollback policy: preserve old agent config revision and older skill versions. Verify current authoritative execution state, source SHA, original-agent failing operation, negative auth, review and COO handoff before closing a real root.

## v72 follow-up — confirmed fixes and important failed regressions (20 October 2026)
- Persisted new external Harness entry file at `wiki/agents/harness/AGENTS.md` through WikiCreatePage and switched the actual agent instructions bundle with PatchAgentInstructionsBundle; exact readback: mode=external, rootPath=/paperclip/instances/default/data/wiki-root/wiki/agents/harness, entryFile=AGENTS.md, 5,175 bytes, SHA256 e30b390b55136bce8cf59535d6a92400a608b2790c5597f040d64f87fc5ecab7, warnings=[]; previous managed AGENTS.md (10,570 bytes) preserved for rollback.
- Root cause of failed managed file edit: paperclipUpdateAgentInstructionsFile's exposed schema omits `baseHash` required by the backend, so create returns HTTP 422 `Read the file and supply baseHash (null for a new file)`; attempting to include baseHash:null at caller also failed. NO write committed, no repeated retries. Fix MCP wrapper schema/serialization and add create/update optimistic concurrency tests, not a human access form.
- Harness skill harness-task-recovery updated to v72 (current version c79ee56c-588b-4e19-aa5b-bce2441ecd70) with an explicit safety case against broken reconcile/cancel loops and instruction setter schema defect.
- Detached unrelated `durable-work-products-cases` skill from the Harness agent only: desired skill count 17 -> 16; core recovery and triage skills still INSTALLED. Weekly skill-improvement routines remain attached; no company-wide removal.
- **Observed source-level BUG, reproducible:** With KOMAA-850 status blocked + credential execution_hold + first-class done predecessor KOMAA-1086, `paperclipReconcileIssueExecution(apply:true)` cancelled a queued run but moved the issue to todo, despite the active hold. A newly queued run appeared. Direct status=blocked without a first-class descriptor was rejected 422. Repaired authoritative issue with a truthful CTO-agent-owned unblockDescriptor explaining legacy opencode_local CTO gateway/token bleed and Supabase network, then set status=blocked; readback status blocked, hold credential, executable=false, relation preserved. A standalone board cancellation of the next queued run immediately caused ANOTHER queued run (different run ID) while status remained blocked. Do NOT repeat; this is a backend wake/retry admission defect. Add server regression on held issue status invariance plus queue cancellation idempotence/fingerprint latch. Existing queued run is not runnable and does not equal delivered work.
- **Not yet validated:** after-v72 original-model-run effective prompt size and 24h timeout/retry drop, atomic cross-agent workspace isolation, exact same original-agent operation E2E, and stable source-enforced cancellation under hold. Do not mark these fixed until actual negative/positive tests pass.

## v76 follow-up — scheduler slot admission + queue resurrection (20 October 2026, 20:05–20:35 UTC)

### Verified live regression (two Harness runs at `maxConcurrentRuns=1`)
- `d9c3223f-96c5-452f-8db8-14ab387031c2` (KOMAA-1033): started 19:54:11Z, cancelled 20:09:43Z (`issue_reassigned`).
- `e17b779c-a716-4984-8438-8f46307136eb` (KOMAA-765): started 20:04:37Z, cancelled 20:24:01Z (`issue_reassigned`).
- Overlap 20:04:37Z–20:09:43Z (~5 min) on two distinct issue workspaces, with `runtimeConfig.heartbeat.maxConcurrentRuns=1`.
- Run events of `e17b779c`: "Scheduled retry became due and was promoted to the queued run pool" 18:59:33Z → "run started" 20:05:32Z → `adapter.invoke` 20:05:32Z. The due retry waited 66 min in the queue and then started while another run of the same agent was already live.

### Root cause A — the per-agent slot is not enforced at claim
- The slot exists in exactly one path: `server/src/services/heartbeat.ts:20128-20133` (`startNextQueuedRunForAgent`): `availableSlots = max(0, policy.maxConcurrentRuns - countRunningRunsForAgent(agentId))`, `if (availableSlots <= 0) return []`.
- The claim chokepoint does not consult it: `heartbeat.ts:17401` `claimQueuedRun` and `:20354` `executeRun` flip a queued row to `status="running"` with no agent-slot check. `countRunningRunsForAgent` is called only at `:18206` (agent status) and `:20128` (queue pump).
- Direct dispatch reaches that chokepoint without the pump: `:15187` native restart recovery, `:19221` persisted native session resumption, `:20310` scheduled native session resume, `:20381` `executeRun` → `claimQueuedRun`.
- The scheduled-retry gate has no concurrency rule: `server/src/modules/run-dispatch/domain/policy.ts` `ScheduledRetryGateErrorCode` has no slot/concurrency code, and `modules/run-dispatch/` has zero references to `maxConcurrentRuns`.

### Root cause B — board cancel is followed by an immediate new run for the same fingerprint
- `server/src/services/issue-rewake-throttle.ts:159-166` breaks the no-progress streak on every non-`succeeded` run ("a failed/cancelled/interrupted run breaks the streak"), so a cancelled run never extends the streak and the throttle never engages. The precondition for resurrection is that the issue is still assigned/`in_progress`.
- Observed pairs (cancel → new runId for the same issue, same second): `e4c0225d`→`1b3703c8` (19:59:45Z, issue 052e8883), `a1652943`→`b34db002` (19:59:48Z), `37262fae`→`6c3fd1b7` (19:59:50Z), `2b7d5ed6`→`c90256c8` (19:59:52Z), `239135e0`→`b4d6a749` (19:59:54Z). One earlier queued run stayed gone because its issue reached a terminal status — consistent with "still assigned" as the resurrection precondition.

### Scope decision (no Core edit, no fake overlay)
Both defects are in Paperclip Core: the heartbeat claim chokepoint and the re-wake throttle. The MCP gateway cannot enforce either — it observes tool calls after a run already exists, and the claim/retry/rewake hooks never traverse it. No Core file was modified; a board approval with exact files, lines and the proposed failing regression was raised instead. The in-scope MCP workspace-isolation candidate is unchanged (SHA `ba6f534ebbcbabcf5c33ffb6afa73dfb64e3fa92f732e7f1d70eacb8c480c56e`, 404/404 vitest, tsc clean) and stays undeployed.
