---
title: CONTEXT-FIRST execution — kontrakt wykonawczy
type: concept
tags: [kontrakt, wykonanie, startup-budget, context]
sources: [raw/WSPOLNY_KONTEKST.md]
created: 2026-08-20
updated: 2026-10-20
---

# CONTEXT-FIRST execution

## Startup order
`wake delta / issue → role invariants → one domain source if needed → targeted CURRENT verification → execution`.

Do not reconstruct context already present in the runtime packet.

## Anti-duplication rule
A heartbeat may contain overlapping layers: role instructions, wake payload, issue description, continuation summary and runtime execution contract. Treat them as layered deltas, not five documents to re-process.

- Issue description = objective/acceptance source.
- Wake/comment delta = newest change and highest-priority action.
- Continuation summary = resume pointer: recent actions, touched files, blockers, next action. If it repeats issue content, do not re-read/restate the duplicated part.
- Runtime execution contract = generic liveness/autonomy/disposition rules. Role Wiki must not duplicate it.
- Role AGENTS = only role-specific ownership/boundaries + pointers to lazy skills.

## Context budget
Default run needs only current issue/delta, role boundary, one relevant domain contract and exact files/runtime evidence.
No full Wiki/PRD/repo/thread preload. At most 2 broad discovery operations before targeted reads.
Repeated >50k-token generations are a warning; >100k or turn-budget exhaustion requires context/session compression before more exploration.

## Resume/checkpoint
Use durable comments/work products/commits as checkpoints. Resume from the last concrete action and next executable action; do not replay prior tool transcript.
If a session has accumulated broad exploration, checkpoint and continue from the durable summary instead of rebuilding the history in-model.

## Verification
Prefer exact SHA/diff, `rg -n`, bounded file ranges and focused tests. Expand only after a concrete failing signal.

See [[wiki/concepts/agent-context-budget]], [[wiki/sources/wspolny-kontekst]], [[wiki/entities/repo-map]].


## Canonical task-bound routing and independent review contract (2026-10-19)
Authoritative operating model for Żar i Szlif:
1. **Engineer** owns domain implementation, Supabase provider MCP actions in its genuine issue-scoped OpenCode runtime, migration and readback, focused tests and evidence. **CTO** owns architecture, authoritative dependency DAG, technical documentation, design decisions, independent candidate-SHA review and acceptance; CTO is never the routine SQL/migration executor. **Harness** owns MCP/adapter/connection/host/identity-context repair; **COO** owns task dispatch/WIP and routing, not domain coding/review.
2. Before a product issue is executable, persist its real assignee and the named independent reviewer stage. For KOMAA-793: implementer **Engineer** (`3fe90c23-8386-40d5-b0a8-52d8c40f812e`), reviewer **CTO** (`ff703eba-3c3d-46f0-b265-df0db1101a19`), reviewPolicy=`not_creator`; retain existing KOMAA-790/KOMAA-850 dependencies and credential/release safeguards. Do not create duplicate tasks. COO/CTO must perform only authorized control-plane mutations and confirm GetIssue/GetDependencyGraph/GetReviewState readback. Current persisted assignment differs and requires actual write.
3. A wake must bind the exact issue, current assignee, authorized runtime identity and *own live* `PAPERCLIP_RUN_ID`; verify `PAPERCLIP_TASK_ID`, `run.issueId`, `agentId`, and `status=RUNNING` before tool discovery or any mutation. Generic `WakeupAgent(on_demand)` runs without issueId are **not** task-bound: their `succeeded` status does not advance a product issue. Never reuse an unrelated/cancelled continuation session (observed Engineeer resumed cancelled KOMAA-871); isolate/new-session with actual issue association.
4. MCP connector discovery such as `PAPERCLIP_RUNTIME_TOOLS_CONNECTIONS_SEARCH_URL` can refuse unbound runs with `Connection requests require a task-bound heartbeat run`. Thus absence of Supabase in Paperclip-native GetAgentEffectiveTools, or in an unbound OpenCode run, **does not establish absence of Engineer's Supabase MCP**. Verify native runtime connection/tools/list plus one harmless authenticated Supabase read in the task-bound Engineer run. Handle real denial via Harness using existing KOMAA-850; no user-facing connector-choice question.
5. `paperclipUpdateIssue`/review-stage mutation requires authorized board credential OR the caller's *own live issue-scoped run*, not another agent's or a finished run ID. Current external COO MCP session exposes `canAssignTasks:true` but `GetCurrentOperatorRun.runId=null`, and a direct PATCH failed with `RUN_CONTEXT_REQUIRED`. Operator-runs API is removed in Paperclip 2026.1012.0. The MCP gateway must route authorized board actions via the existing validated board credential capability and preserve per-issue authorization for agents; never forge run IDs, turn off guard or mint an unrestricted operator session.
6. Effective-tools read model must be context-sensitive: `GetAgentEffectiveTools.executableNow` and `VerifyAgentTool.states.EXECUTION_CONTEXT_VALID` must NOT return true for `requiresRun=true` when no valid task-bound active run exists. Generic company-read reachability is `PROBED_SUCCESSFULLY=false`, not a positive authorization proof. Build an explicit false-positive regression.
7. Technical prerequisites (provider connection, runtime projection, issue control-plane repair) must be routed to Engineer/Harness/COO. A user/Board `ask_user_questions` is disallowed for routine technical choices; use only for a proved, nondelegable individual OAuth consent or user business decision. KOMAA-793 question `258c03d3-7a2a-4307-aabf-df2bf779a6d8` is invalid and pending; current `accept` and `reject` on `ask_user_questions` return 422, requiring an authorized lifecycle endpoint or MCP compatibility fix with persisted readback, not silent dismissal.
8. Fail-closed acceptance test suite: (a) authorized Board/issue scoped assignment and reviewer PATCH persists; (b) unauthorized/foreign/terminal/no-run writes fail 401/403; (c) issue-scoped Engineer connection discovery succeeds or gives a real actionable 401/403; (d) generic wake does not replay cancelled issue; (e) role review independence is enforced; (f) technical question admission avoids human routing and stale existing question is resolved by a supported lifecycle; (g) no removed D1 path; (h) no welcome email until proven historical reconciliation, testing and release approvals. Verify through LIVE public MCP tool calls and authoritative issue readback, never only unit tests or prompts.


## 2026-10-19 — hard execution admission, readback and evaluator truth (observed in Langfuse)

This section is the canonical issue-scoped operational delta. Role-specific skills may refer here rather than copying this contract into every AGENTS.md. No prompt bypasses API security, review or deployment gates.

**Pre-call admission (fail-closed):** Determine {actor principal, signed own live runId, issue UUID, workspace owning issue, effective exposed tool, schema version, requested scope, idempotency key and expected postcondition}. Resolve all UUIDs/enum values/numeric limits from live MCP schema and exact read-only resource IDs. **Never** substitute another agent's runId or a fictional Board key. Verify the run is both live and bound to the issue/workspace. If caller is a generic external operator with runId=null, do not attempt cross-issue writes through an agent key: obtain a legitimately authorized Board operation through the approved control plane (Harness/CEO), not an identity switch. A declared/exposed tool is not proof of executable issue-scoped permission.

**Workspace:** List the real authorized workspace root first. All file operations take workspace-relative paths. Absolute host worktree paths and assumed src/ folder names are invalid. Limit search/query output (normally <=8KB) and avoid unbounded ripgrep JSON (>64KB observed). Same-issue workspace and checkout are mandatory; do not test another issue's workspace with your own runId.

**Error decision table:** 400/422 INVALID_ARGUMENTS, invalid UUID/sourceIssueStatus enum/timeout bound => caller schema fix, once, with corrected parameter. 401/403 RUN_CONTEXT_REQUIRED, JWT/header mismatch or SCOPE_DENIED => no replay, grant/issue-scope diagnosis by the authorized owner. Board-only CONFIGURATION_MISSING => Board authorization gate, never borrowed credential. 404/PATH_DENIED => read/list target and correct path/ID once. 409 stale review or conflicting state => read canonical state, no forced todo/PATCH fallback. 5xx/unknown commit => **read back** target and idempotency ledger BEFORE retry; known successful mutation is never repeated. Do not classify all errors as harness bugs; distinguish caller input from adapter projection defects.

**Result contract:** For each mutation record before target state, validated call + source run/correlation ID, after readback and irreversible side effects, artifact/version/candidate SHA, focused negative regression, named independent reviewer and deployment state. A successful tool/LLM process, positive observation-local evaluator or status flip alone is **0 verified delivery**. Never mark in_review with only a generic anyone confirmation. CTO validates candidate DAG/docs/technical evidence; Engineer implements product/Supabase logic; Harness fixes MCP/runtime/host; COO dispatches; CMO approves marketing/consent. Preserve pending named human reviewer stages.

**Observability:** The 2026-10-19 Langfuse sample had ERROR-level schema/scope failures and 4 SKILL_LOAD_FAILED paperclip events. A SKILL_NOT_FOUND event whose error_excerpt includes skill_content is diagnostically ambiguous: compare runtime skill manifest, resolved runtime name, actual skill load tool result and injection before asserting missing installation. Evaluators such as pc_repeated_failed_action, pc_execution_without_delivery and pc_missing_reviewer_detection can return boolean true with comments that actually say no violation; treat labels according to evaluator definition, aggregate by trace/run + authoritative Paperclip state, and never interpret positive heuristics as proof of an incident or delivery.

**Security-sensitive tool output:** Paperclip GetSkillTestRun can return agentConfigSnapshot with sensitive environment values. Project only id/status/output/verdict/cost when summarizing these results; never paste full snapshots into traces, comments or user-visible logs. Harness must repair server-side redaction at the MCP response boundary and add a positive/negative secret-leak regression before any claim of production-safe telemetry.

**Acceptance fixtures:** invalid UUID+enum+bound; JWT mismatched run; cross-issue workspace; absolute or missing path; Board-only credential; 409 named reviewer; 5xx possibly committed; ambiguous skill loader event; evaluator-score inversion; missing independent reviewer; secret exposure in run-test introspection. For each fixture require a negative unauthorized-mutation check and a positive authorized readback. The Langfuse dataset `paperclip-mcp-execution-admission-2026-10-19` contains 9 read-only judgment fixtures; not a substitute for executable E2E. Keep live AGENTS.md synchronization separate from Langfuse staging prompt versions; never call a staged prompt production without persisted Paperclip runtime readback.

## 2026-10-20 — native managed-MCP projection contract and connection-health truth

Verified in the original Engineer principal's own task-bound run (KOMAA-1086). This section is the durable contract, not an incident log.

**Projection mechanism (managed MCP -> OpenCode).** A managed MCP connection is never exposed to the agent runtime as its own `mcp` map entry. The generated per-run OpenCode config exposes exactly one gateway entry, `paperclip-assigned`, scoped to `tools/list` and `tools/call`; the gateway resolves per-connection exposure server-side. Therefore a missing per-connection key in the runtime `mcp` map is by design and is NOT evidence of a lost or empty map; and a non-empty `ctx.runtimeMcp.getServers()` proves only that at least one managed connection was assigned, never that its provider is reachable.

**Per-principal access proof (required method).** Prove access in the principal's own task-bound run with (a) gateway `tools/list` using that run's own scoped token, and (b) one real authenticated provider call that exercises the provider's backing store. `GetAgentEffectiveTools` and `VerifyAgentTool` are NOT an access proof for managed MCP: the effective-tools catalogue enumerates only Paperclip-native tools, so a per-principal filter for a managed connection returns zero and a managed tool reports "tool not registered". That is a false-negative catalogue signal, not a missing grant or a missing projection.
Scope is genuinely per principal: a managed connection installed for one agent can still be absent from that agent's own run-scoped gateway (Harness reported exactly that for its own principal as defect D3 on 2026-10-20), so prove access per principal and never infer it company-wide.

**Health truth.** Transport-level health (gateway `tools/list` and `tools/call` succeed) is necessary but not sufficient. A connection whose provider cannot reach its backing store must not be reported healthy; `healthStatus: ok` while provider calls fail is a false green and is itself a defect. Acceptance of a connection requires provider-level readback, never a registry health flag.

**Discriminator outcome and no-retry rule.** The managed-connection -> OpenCode projection path was proven intact in the original principal's runtime; the observed failure was provider-side (the provider's own Postgres pool could not connect), i.e. a backing-store defect owned by the Harness root KOMAA-850, not a projection defect. Do not re-patch adapter or registration for that symptom: re-patching a projection path proven working is a same-fingerprint retry with no new causal input.
