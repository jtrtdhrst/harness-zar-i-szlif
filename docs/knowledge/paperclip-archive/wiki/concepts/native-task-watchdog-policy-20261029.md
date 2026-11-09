---
title: Native task watchdog — mandatory on real issues
type: concept
tags: [paperclip, watchdog, delivery, governance]
updated: 2026-10-29
---

## CURRENT OWNER STAND-DOWN — 2026-10-29
The owner has suspended ALL task-watchdog automation and routines until explicit reauthorization. All older clauses below that require attaching a watchdog to newly created tasks are **INACTIVE**. Do not create, enable, update or reattach watchdogs automatically. The native DELETE/Remove leaves a disabled audit row, not a live paused configuration; do not replay historical configurations or restore watchers in order to 'fix' this. Do not create routine runs or auto-monitoring tasks. Keep timer heartbeat disabled. These historical instructions remain for future reference only, not active policy.



# Żar i Szlif — mandatory task-native watchdog (no timer heartbeat)

**Owner directive 2026-10-29:** Every newly created or delegated real actionable Paperclip issue MUST have a native `watchdog` configured. This is a task lifecycle observer for stopped work, **not** a timer/cron/heartbeat mechanism. Agent `runtimeConfig.heartbeat.enabled` stays false; `wakeOnAssignment`, `wakeOnDemand`, `wakeOnAutomation` may be true.

## Required create/assign contract

1. Determine original issue assignee, parent/ancestor owners, and hierarchy. Before `paperclipCreateIssue`, select watcher: closest assigned parent issue owner when independent and suitable; otherwise new assignee's direct supervisor (`reportsTo`); then closest valid supervisor/CEO. Never make a reviewer the author of their own acceptance; watchdog and independent review are separate roles.
2. Create the real issue *once* with `watchdog:{agentId, instructions}`, alongside `assigneeAgentId`, actual causal `blockedByIssueIds` only when real, and an independent typed review stage when needed.
3. Immediately `paperclipGetIssueFieldDetails(issueId, sections:['watchdog','relationships','execution'])`. Verify watchdog.status=active and exact watcher ID. If not persisted, use native `paperclipManageIssueWatchdog(create|update)` with authorized issue context, read back again; **do not dispatch an unwatched task**.
4. Reassignment/reparenting requires re-evaluating watcher and updating it when ownership changes; verify again. For existing active issue with correct watcher, DO NOT write again.
5. Native watchdog reacts to genuine stopped-subtree state and fingerprints. Deduplicate identical events; recovery is bounded, and it must preserve existing issue, reviewer and authorization. It never marks code delivered, approves review, merges PRs or claims production success.
6. Do NOT attach recursive watchdogs to native generated `originKind=task_watchdog` issues or routine executions. Do not create redundant watchdog child tasks or automatic timer routines.
7. When an authorized source issue cannot get a watchdog, report precise native authorization/handler failure and do not fake success or bypass access controls.
8. Technical comments, evidence, test names, SHA and review statuses in English; Polish brand/user-facing copy unchanged.

## Review routing
- Product code, product MCP, Plasmic component integration: CTO as qualified independent technical reviewer; UI QA for browser/functionality and CMO for brand content when relevant.
- Infrastructure MCP, gateway, runtime, Coolify/Docker: CHO independent technical reviewer, including Harness changes.
- Mascots (Mascot Designer) and non-character assets (CPO): CPO specialist review (characters from Mascot Designer only), final CMO approval for public-facing visuals where required.
- Delivery & Release Manager coordinates and verifies real review/liveness; never self-reviews, never uses watchdog as review or release authorization.

## Non-guarantee / platform limitation
Current Paperclip `paperclipCreateIssue` exposes `watchdog` as an optional field; this document and agent policies enforce workflow discipline but do **not** implement a server-global database constraint. For hard "cannot-create-without-watchdog" enforcement, add an upstream-compatible server-side validation only through a separate authorized reviewed source change, not by mutating Paperclip Core in this configuration.

## Acceptance evidence
Each real new issue: `issueId`, `assigneeAgentId`, `watchdogAgentId`, `watchdog.status=active`, native independent reviewer if required, actual dispatch run, and E2E delivery evidence when closed.
