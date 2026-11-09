---
title: Agent context budget — runtime + Wiki
type: concept
tags: [context, langfuse, agents, runtime, performance]
created: 2026-10-04
updated: 2026-10-06
---

# Agent context budget

Purpose: keep agent context small enough to execute, while preserving role, safety and acceptance semantics.

## Current 2026-10-21 consistency checks (runtime readback required)
1. **Native truth precedence:** the issue's authoritative current status, issue_relations, executionHold and typed review stage outrank any continuation-summary status, previously captured comments or historical Board snapshots. A stale summary is historical evidence only and must never restore `blocked`, reviewer, repo or deployment state.
2. **Skill reality:** a library skill, `desiredSkills`, previous install receipt, agent capability prose or wiki claim is NOT current executable skill. Compare `GetAgentSkillSet.entries` and verify required key `state=installed` *and real current agent-runtime load*. Shared `~/.claude/skills` pruning in **KOMAA-431** is unresolved until isolated/union install-root source repair, two distinct agents' readback after A/B/concurrent sync, zero missing desired entries and persistent live canary. Until then no individual or global skill resync.
3. **Routine dependency admission:** before a routine refers to a company skill, verify that exact skill is effectively installed for its assignee. If missing, stop without pretending work was executed; route one normalized signal to already-existing KOMAA-431 and do not create duplicate issues or re-wakes. The company skill library existing is not enough.
4. **Conditional stage:** do not preload archived role AGENTS, backfill entire previous session, older vXX policies or unrelated skills. Only entry AGENTS, current wake/issue, one required on-demand skill and causal files/tests. Old archived pages are for rollback only.
5. **Measured result:** quantify runtime prompt chars, input/cache-read separately, accepted outcome, and negative authorization. A smaller markdown file is **configuration compaction**, not proof of lower model usage until measured new runs show it; a patch or PASS without live identity is not deployed.

## Runtime layers
Paperclip/OpenCode can supply:
1. role `AGENTS.md`;
2. wake/comment delta;
3. issue description;
4. continuation summary;
5. generic runtime execution contract;
6. prior session/tool history.

These layers must be complementary. Do not copy the same execution/autonomy rules into role Wiki, skills and issue text.

## What stays always loaded
Role AGENTS contains only:
- ownership and hard boundaries;
- acceptance/review identity rules;
- critical safety/repository boundary;
- pointers to canonical on-demand skills/pages.

Detailed procedures, examples, runbooks, release recipes and long checklists belong in on-demand skills or domain Wiki.

## Resume rule
Wake delta wins for the next action.
Issue description defines objective/acceptance.
Continuation summary is a checkpoint, not a second issue description. Consume recent actions/blockers/next action; ignore duplicated historical narrative.
Do not refetch the full thread when `fallbackFetchNeeded=false` unless a specific missing fact is required.

## Exploration budget
- max 2 broad discovery operations;
- then exact file/function/SHA/error reads;
- checkpoint before starting another investigation branch;
- same deterministic failure + no causal delta => no retry.

## Review budget
- Review exact SHA/diff + existing evidence first.
- A reviewer should reach PASS/FAIL/CHANGES before spending time on control-plane closeout mechanics.
- Once the verdict is known, persist the verdict and exact SHA first; API/repo archaeology after a known verdict is waste unless required to perform the final mutation.
- Repeated technical re-verification of an unchanged accepted SHA is forbidden without a new causal signal.

## Langfuse guardrails
Track production `opencode.generation` by agent/task:
- repeated total context >50k = investigate duplication/session growth;
- >100k = high severity;
- turn-budget exhaustion after broad reads = force checkpoint + narrower continuation.

Separate fresh `input` from `cache_read`. Large aggregate `totalTokens` dominated by cache-read indicates accumulated session history/throughput pressure; it is not by itself proof of a bloated first-turn prompt.

Use cache-read growth as evidence of accumulated session history, not as justification to add more prompt text.

## CURRENT verification boundary
For Paperclip/platform work, **candidate branch, source/master and deployed runtime are different states**.

Do not mark work CURRENT/live from a committed or reviewed candidate alone. Verify, as applicable:
1. exact accepted candidate SHA;
2. whether it is integrated into the governed source/master path;
3. runtime/server commit identity;
4. active overlay/localfix identity and whether it is stale;
5. required post-deploy live evidence.

`PASS` or `done` must not imply deployment when the runtime identity still points at an older build/overlay.

## Wiki hygiene
Wiki stores durable knowledge, not run transcripts.
Prefer one canonical page + links over repeated contracts across role pages.
When runtime already enforces a generic rule, role Wiki should point to it rather than restate it.

## Historical Langfuse baseline — 2026-10-14 (not CURRENT)
100 latest GENERATION observations/agent, scoped by metadata `attributes.paperclip_agent_id` (not `userId=operator`). Per-generation context `total` includes cache_read; units are tokens. CTO p50/p95 130,504/212,422; CMO 48,135/99,031; COO 32,731/49,625; CEO 35,479/47,704. These are NOT billed-uncached costs nor validated savings. Exact observations and source notes: issue KOMAA-731, doc `langfuse-clevel-20261014`.

Historical activation gate recorded on 2026-10-14: accepted context-economy candidate from KOMAA-731 was then not proven live; 2026-10-14 host build still 65ec059b. Reuse the canonical issue, no new clones. Distinguish prompt/role optimization (3 live instruction edits verified) from runtime session-compaction and source/overlay activation (pending). **Do not enable a hard tool-call ceiling as an optimization**: current configs have `turnBudget.enabled=false` and KOMAA-767 explicitly removes the hard ceiling. Keep causal stop/checkpoint/observability without automatic kill on call count.
