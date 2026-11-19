---
title: Delivery DAG orchestration v65
type: concept
status: active
updated: 2026-10-19
---

# Żar i Szlif — native delivery DAG, useful subtasks, review and continuation

## Source of truth
Installed company skill `delivery-dag-orchestration` (all 11 agents); DAG builders additionally follow `issue-dag-governance` where enabled. Agent-specific AGENTS.md instructions and canonical `paperclip-router` are mandatory. Native Paperclip `issue_relations`, `executionPolicy`, review state, effective tool authorization and `GetExecutionEligibility` supersede summaries, status projections and prompts.

## Operational decision
A single coherent owned outcome is SINGLE_TASK; do not split into artificial test/docs/review/wakeup tasks. Create a DAG only when a separate owner, artifact, real consumed prerequisite, parallel writer or independent release boundary exists. Prefer 2–5 real deliverable children with accountable assignee, concise DoD, exact source/workspace, docs disposition and named independent reviewer. Reuse present children. Watchdogs and first-class review stages are governance mechanisms, not default implementation subtasks.

## Mutations
CTO creates technical DAG and assigns specialists; CMO creates cross-domain marketing DAG; COO routes and dispatches but does not design implementation; Harness repairs execution environment only. On child CREATE persist parentId, assignee, DoD, reviewPolicy not_creator, executionPolicy named reviewer in SAME request; after that persist only genuinely causal blockedBy edges via native graph tools and ValidateDAG + readback. ParentId NEVER implies blockedBy. Do not create duplicate children or false edges for capacity, review, environment outage or external wait. For one-writer artifacts, enforce isolated workspace/branch before parallel dispatch. Authorization 403/409/422 fails closed.

## Execution
COO sole hourly DELIVERY OPERATOR — EXECUTION: assess bounded roots, route missing DAG decision only if justified, dispatch eligible parallel frontier via native provider/runtime preflight, no duplicate live/queued/wake. After independently accepted upstream child, recompute successor eligibility and wake once. Harness sole hourly technical blocker recovery repairs canonical root, verifies original-agent native access and hands COO verified READY proof; does not take domain work. CTO/CMO/UI QA accept exact artifacts as independent reviewers, not by status. Parent closes only after all required outputs and integration/live/docs/approval gates are accepted, with immutable evidence.

## Acceptance checks
(a) no child for one-owner unit, (b) real child persisted for multi-owner unit, (c) no fake parallel dependency, (d) downstream blocked until accepted prerequisite, (e) reviewer admitted and truly independent, (f) successor wakes exactly once on accepted prerequisite, (g) duplicate fingerprint no new child, (h) Harness repair doesn't steal product work, (i) 403/409 no unauthorized mutation, (j) parent remains open until genuine accepted end-to-end product DoD. A completed routine, passed tool call, watchdog note or UI status change is not product delivery.

## Native task-watchdog lifecycle and admission — v69 (2026-10-20)

This section is normative for DAG authors (CTO/CMO), COO dispatch and Harness environment recovery. It documents the required native Paperclip behavior, not a claim that the currently deployed server fully enforces it. Canonical implementation root: KOMAA-1031; related review admission root: KOMAA-849/865.

### Scope and eligibility
- A task watchdog is an event-driven **observer of a meaningful delivery root/subtree**, not an hourly heartbeat, routine, review stage, approval participant, independent release signoff, or general-purpose monitor. Ordinary leaf issues normally receive neither a watchdog nor a synthetic watchdog-review subtask.
- Use at most one active watchdog for a given independently owned recovery scope. Avoid a watchdog on a descendant already covered by its parent unless an independently operated subtree demonstrably needs one; record why coverage is disjoint. Read current active watchdogs and ancestor hierarchy before PUT.
- Set a dedicated, authorized recovery owner: COO for orchestration/dependency routing or Harness for a proven technical-runtime recovery scope. Never choose the current domain implementer as an automatic substitute for independent acceptance.
- Trigger only when authoritative native subtree classification is genuinely `stopped` and there is a **material new causal fingerprint**. A valid active/queued owner/reviewer run, scheduled retry, unresolved first-class blocker, or outstanding genuine human approval is not permission for a blind wake. Waiting on authorized human approval/interaction must classify `waiting_on_human`.
- `executionPolicy.monitor` is a distinct one-shot timer/external-condition check; it must have a real `nextCheckAt`, service/event purpose and bounded max attempts. Do not schedule synthetic heartbeat monitors to replace watchdogs.

### Isolation and fingerprint invariants
- The watchdog review issue (`originKind=task_watchdog`) is control-plane **observer state**: its creation, parent/child bookkeeping, temporary blocker edge, comments and terminal transition MUST NOT alter the watched work fingerprint or wake the watched domain owner.
- Exclude watchdog-owned observer relations from the watched issue's `blockerIssueIds` and from material stop snapshots. Fingerprint should change only when executable input, real first-class dependency, legitimate approval/interaction, stage or assignee changes.
- Identical fingerprint with no new causal input: zero new watchdog issue/run, zero duplicate owner/reviewer wake, zero duplicate comment/child. Never clear true blockers or fabricate parentId/blockedBy relations to make progress. Approval decided: exactly one native continuation wake after first-class decision and eligibility check.
- For confirmed 409 `REVIEW_STATE_CONFLICT`, refresh current review state once and route to KOMAA-849/865 with exact stage/actor/error. Do not downgrade status, force PASS, self-review, or mutate reviewPolicy to weaken the gate.
- A watchdog may complete its own control review with a truthful disposition while the watched product issue remains blocked/review-pending. Never count this as accepted product delivery.

### Bounded recovery transaction
1. Read watched root/subtree (parent hierarchy + authoritative `issue_relations`), GetExecutionEligibility, GetReviewState, live/queued runs and existing watchdog/recovery fingerprints; inspect the minimal stopped frontier only.
2. Determine exact cause, original executor, effective native tools **in the original agent runtime**, immutable failure fingerprint and actual dependency/approval gate. Existing live execution or same previously reviewed fingerprint ⇒ **NO ACTION**.
3. For a recoverable technical defect reuse the canonical Harness/CTO root, perform one authorized reversible minimal repair, negative authorization test, independent readback, and preserve security/release approvals. Do not create duplicate technical/review meta-issues.
4. Re-read graph, current stage/reviewer, original-principal failing-operation probe and scheduler eligibility. COO may wake the original owner ONCE only if all gates are satisfied and no run is queued/running; otherwise record the precise owner and event that must change.
5. Record concise English before/after evidence, source/commit or config SHA, tests, run IDs, next owner and required continuation signal. Product Polish content remains Polish.

### Required RED/GREEN regression tests before production acceptance
1. Watchdog observer issue closes ⇒ zero `issue_children_completed` or `issue_blockers_resolved` wake on watched owner solely due to observer bookkeeping.
2. Add/remove watchdog-owned observer relation ⇒ material stop fingerprint remains stable.
3. Pending linked Board/user approval as only remaining path ⇒ `waiting_on_human`, zero watchdog issue/run/owner wake on repeated scheduler ticks.
4. Authorized approval decision ⇒ exactly one continuation wake, preserving named independent reviewer stage.
5. Three re-evaluations of unchanged fingerprint ⇒ no additional runs, cards, comments, issue edges or wake requests.
6. Real new failure/input change ⇒ one bounded watchdog response with idempotent readback; active owner/run ⇒ no duplicate wake; still-blocked dependency ⇒ no wake.
7. Native `in_review` 409 conflict ⇒ fail-closed, no stage/status bypass or false product PASS.
8. Verify public deployed server version and first-party MCP readback after independently approved source candidate/release; local test PASS and wiki update alone are **not production-ready**.

### Remediation state on 2026-10-20
Read-only root evidence for KOMAA-1031 reports a source candidate implementing observer isolation, `waiting_on_human` and idempotency, but production deployment and first-class acceptance remain unverified. Four overlapping watchers (KOMAA-996, KOMAA-1003, KOMAA-1084, KOMAA-788) were disabled and read back; the deliberate retained root watchers were KOMAA-1081 and KOMAA-849, while KOMAA-1005 remains active pending a supported authorized change. No change to Paperclip/OpenCode Core is authorized merely by this documentation update.

## Baseline 2026-10-19
707 non-routine issues, 240 child tasks; only 8 of 74 issues created since 2026-10-18 were children, all watchdog-review tasks. Root KOMAA-774 authoritative DAG validation had 17 nodes, 4 relation edges and 0 anomalies. Baseline is informational only, not a proof of all-company workflow health. Measure accepted product outcomes and actual resumed successors after policy rollout.

## Language and security
Internal operational text English; preserve approved Polish Żar i Szlif product copy. Never bypass review/approval, expose credentials, self-approve or deploy/sent campaign without governed authorization. Do not modify Paperclip/OpenCode Core as part of this policy rollout.
