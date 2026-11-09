---
title: Definition of Done — delivery, review, docs, evidence
type: concept
tags: [dod, delivery, governance, review, documentation]
sources: [raw/WSPOLNY_KONTEKST.md]
created: 2026-08-20
updated: 2026-10-04
---

# Definition of Done

`done` = verified delivered outcome, not merely a successful process, commit, branch, PR or author claim.

## Repo-write delivery
`issue workspace → implementation → focused required checks → candidate_sha → required independent review of that SHA → governed integration → ancestry/deploy/live evidence required by target → docs disposition → done`.

- PASS binds to the exact `candidate_sha`; affected changes after PASS require re-verification.
- Implementer does not self-approve governed repo writes.
- Merge/release authority follows the role/repository contract. Never claim push/merge/CI/deploy/live acceptance without evidence.
- Review, docs and recovery stay on the source issue unless a separate independently valuable deliverable is created.

## Independent review
Reviewer starts from immutable candidate/diff and existing verification. PASS or precise requested changes; do not repeat the executor's full exploration without contradictory evidence.

## Documentation disposition
Every closeout has `DOC_IMPACT=YES|NO`.
- YES: update only affected canonical Wiki pages using read-before-write + optimistic locking; evidence names page and changed durable contract.
- NO: give a scope-based reason that existing Wiki already matches post-change behavior.
- Do not create one Wiki page per task and do not copy ephemeral logs/transcripts into Wiki.

Fail closed when required review, delivery evidence or docs disposition is missing.

Generic issue-state/autonomy mechanics come from the runtime execution contract, not this page.
See [[wiki/concepts/agent-context-budget]].

## Issue admission: Definition of Worth (2026-10-15)

MANDATORY PRE-CREATE GATE. A new issue requires a unique, measurable outcome not already delivered or owned by another canonical issue. Security and production hazards count as material value even without commercial ROI. Task count, utilization, comments, repetitive audits and wrapper coordination are not outcomes.

Before CreateIssue, inspect current target/runtime evidence, relevant existing issues, parents/children, last accepted SHA, real blocker and live runs. Require six concrete fields: OUTCOME (observable user/system change); EVIDENCE (before/after, test, SHA/provider ID, independent reviewer as needed); UNIQUE DELTA (why existing issue IDs cannot absorb work); OWNER+NEXT ACTION (authorized and executable); VALUE/COST (user outcome, incident risk reduction, critical-path unblock or recurring token/operating savings versus implementation and review cost); TERMINAL RULE (acceptance, cancellation/supersession and proof). If any field is absent, refine the current canonical issue or record NEEDS_EVIDENCE without creating a duplicate.

Implementation, tests, docs, reviewer and release checks belong as stages/gates on the source issue unless they produce separately useful, independently acceptable artifacts. Do not create issue purely to re-review old SHA, poll unchanged 403/OAuth, restate blocked conditions, create status report, coordinate already-owned tasks, or fix an already validated step. ONE outcome/root cause -> ONE canonical owner issue. If superseded, merge distinct unmet acceptance, cancel duplicate with evidence and stop its queued runs. Never mark a duplicate done.

## Native DAG admission and integrity (2026-10-15)

Add a blockedBy edge only when downstream cannot validly pass its acceptance without the exact uniquely-owned upstream artifact/decision. Document the acceptance predicate and source UUID. Before mutation read GetDependencyGraph (direct blockers and subtree), current execution state, ancestors/descendants, and terminal evidence. Reject self edges, cycles, transitive redundant edges, status/meta wrapper blockers, parent-child completion deadlocks and edges to an already proven outcome. A parentId is organizational hierarchy, NOT a blockedBy edge.

IMPORTANT LIVE DIAGNOSTIC DEFECT 2026-10-15: ValidateDAG returned edgeCount=0 while GetDependencyGraph showed real edges (e.g. KOMAA-774 blocked by 786 and 790, KOMAA-788 blocked by 776). Never infer edges are absent from validator counts or list projection alone. Cross-check direct graph; fail closed on mismatch until validator is patched and regression-tested. Apply atomic PatchDependencyGraph only after verified before/after, then re-read both ends.

External credentials, Board/OAuth approval, human review, host safety, provider failure, worktree contention, concurrency, scheduled monitoring and reviewer capacity are NOT synthetic product DAG edges. Use explicit unblockDescriptor, review stages, monitor, execution hold, provider/runtime eligibility and causal retry gates. Real external wait must stay blocked until real evidence changes. Do not add a ticket to represent absence of credentials if a canonical owner/wait already exists.

Upstream accepted -> recheck real downstream DAG and evidence -> clean stale edge if appropriate -> eligibility+preflight -> single eligible wake. No forced reruns; preserve human/security/release gates.

## Terminal and pruning rules (2026-10-15)

Classify KEEP_UNIQUE, VERIFY_COMPLETE, MERGE_CANCEL, WAIT_EXTERNAL or NEEDS_EVIDENCE. VERIFY_COMPLETE requires target-current independent proof, not agent claim. MERGE_CANCEL requires the survivor to own all nonredundant acceptance; preserve evidence, and use native SupersedeIssue when safe to migrate dependents. After cancellation verify survivor, real blockers, no queued/running zombie run on retired issue. Never cancel active healthy work or valid P0 safety/human gate to improve counts.

Only accepted unique outcomes and critical-path impact count as delivery; comments, issue creation, status flips, successful agent process exits and standalone reports are not delivery.

## Agent Git/branch delivery contract (2026-10-15)
For REPO_WRITE, mandatory issue-owned branch/worktree, commit/push admission, exact SHA reviewer/merge and non-destructive GC are canonically specified at [[wiki/concepts/agent-git-delivery-policy]]. Stage definitions above remain authoritative for acceptance; GitHub PR, CI and native Paperclip controls must enforce, and no skill/prompt is accepted as proof of server enforcement.


## Pre-delegation DoD contract and reviewer agreement (2026-11-07)

**Problem prevented:** a C-level planner delegates a broad outcome, the implementing agent produces a reasonable candidate, and a different-model reviewer repeatedly rejects it because release proof, inaccessible credentials, or newly invented requirements are conflated with the implementation DoD. Model diversity is deliberate and MUST remain; moving acceptance criteria after execution is not.

### A. Mandatory fixed contract BEFORE assigning or waking an executor

The accountable lead (CHO for Harness Engineer, CTO for Engineer/MCP Engineer, CPO for Mascot Designer) must define and explicitly own this compact acceptance record in the canonical issue description or versioned issue document, before implementation. A wiki link alone, a parent epic with a broad goal, or an unversioned comment is NOT an acceptance contract.

| Key | Required value |
| --- | --- |
| \`DOD_VERSION\` | Version/record hash; timestamp; creator; reviewer; executor; parent/implementation/release issue IDs |
| \`OUTCOME\` | One demonstrable, independently valuable change; non-goals and exact paths/repo/services |
| \`PREDICATES\` | Numbered \`DOD-01..\` binary PASS/FAIL checks, with observable threshold and evidence command/link per predicate |
| \`RESPONSIBILITY\` | For each predicate, one of \`EXECUTOR\`, \`REVIEWER\`, \`RELEASE_OWNER\`, \`EXTERNAL\`; dependencies preflighted against real credentials/tools/workspace |
| \`GATES\` | \`IMPLEMENTATION\` (diff, tests, security), \`INDEPENDENT_REVIEW\` (exact SHA), \`RELEASE\` (merge/deploy/rollback), \`OUTCOME\` (live E2E and parent close) — each with explicit owner |
| \`UNKNOWNS\` | Unproven assumptions, security controls, expected evidence location, and who can resolve each known external dependency |
| \`REWORK\` | Exact failing predicate, reproducible observation, and smallest delta needed for PASS; re-review on new candidate SHA |

**Acceptance-contract handshake:** before working, the executor checks the predicate wording, actionable tool/grant/path preflight and evidence feasibility; the reviewer/lead acknowledges the SAME version for evaluation. If ambiguous, missing a required tool or asking the executor to furnish proof only a release owner can produce, fix the contract/ownership BEFORE spending an implementation run. Avoid extra approval tickets; document on the existing issue. A contractor cannot be held accountable for an inaccessible gate assigned to a different role.

### B. What independent reviewers may reject

The reviewer independently verifies the exact candidate SHA and tests. \`CHANGES_REQUESTED\` must identify (1) the existing \`DOD-xx\` predicate, (2) exact observed failure including file/line/command/CI/trace or absence of explicitly required evidence, (3) reproducible expected outcome, (4) who can fix it, and (5) a bounded next action. A severe NEW security/functional defect discovered by review is valid even when missing from the original checklist, but MUST be logged as \`DISCOVERED_DEFECT\` with concrete exploit/failing case, severity, added versioned predicate and explicit scope ownership; never quietly relabel opinion/preferences as failed DoD.

A missing \`RELEASE\` or \`OUTCOME\` gate does NOT invalidate an otherwise passing \`IMPLEMENTATION\` candidate. Record implementation PASS and keep the release/outcome stage open, creating an independently executable release unit only when it has a distinct owner/output and real dependency. A true code defect does block code approval. Preserve authentic independent review, security denials, required human authorization and SHA-linked CI.

### C. Review disagreement, rework and blocked states

Classify EACH non-PASS into exactly one:
- \`CODE_DEFECT\`: existing predicate or concrete newly discovered defect fails → \`CHANGES_REQUESTED\`, return to original executor with exact repro and one event-driven retry on changed inputs.
- \`EVIDENCE_MISSING\`: specified executor-owned evidence absent despite access → one precise evidence request; no repeated full re-investigation or speculative edits.
- \`ACCEPTANCE_DRIFT\`: reviewer demands something outside frozen predicates and no new material defect → contract correction/second opinion, NOT a defect attributed to executor.
- \`EXTERNAL_GATE\`: genuine missing credentials, production authorization, release dependency, provider availability → named owning party + evidence + wait; do NOT code-reject for another actor's access.
- \`REVIEW_ENGINE_FAILURE\`: review decision/writeback/runtime missing or issue drifts to \`blocked\` without a real blocker → native control-plane recovery; do not hide as implementer failure.

Two consecutive rejections with the same failure fingerprint and no changed candidate/input trigger a bounded lead + competent independent second-opinion comparison of the original predicate against evidence. Change strategy/contract or route the real external gate; no third identical rework run. A configured review limit of 50 is only a safety ceiling, NOT a review strategy. Disagreement never permits fabricated approval, self-review or bypass.

\`blocked\` requires an authoritative unsatisfied dependency or documented execution hold/external gate, a causal fingerprint, its actual owner and an explicit release condition. A bad review verdict or failed status transition is not itself a DAG blocker. If native Paperclip transitions violate these rules, treat it as a **control-plane defect requiring tests and a verified source fix**, not as something markdown alone can enforce.

### D. Acceptance cases to regression-test

1. CHO specifies \`DOD-01\` code test and \`DOD-02\` live deployment by release owner; Harness passes code candidate tests but production credentials are absent: independent CHO code review may PASS the implementation SHA; \`DOD-02\` remains externally gated; no endless \`CHANGES_REQUESTED\` and no false parent DONE.
2. Reviewer discovers actual cross-run grant leak omitted from \`DOD-01\`: rejects with reproduced security defect, versioned delta and Harness-owned test; remains fail-closed.
3. Reviewer asks for a new preference or unrelated system refactor: \`ACCEPTANCE_DRIFT\`, not executor fault, no implementation loop.
4. Same exact candidate SHA and same rejection twice with no new evidence: stop retry, escalate one independent technical comparison; no new ticket or synthetic blocker.
5. Native issue shifts \`in_review → blocked\` with zero real blockers, or first-class review decision is not persisted: classify \`REVIEW_ENGINE_FAILURE\`; preserve genuine reviewer identity/decisions and repair underlying runtime, never raw-PATCH/forged PASS.
6. Acceptance reached only when the explicitly applicable gates have actual native decision, work-product lineage, CI, deployment and live readback. A skill test validates agent behavior; only backend regression plus live issue E2E proves enforcement.

### E. Ownership and operating rule

CHO designs executable, proportionate DoD and reviews Harness code; Harness may challenge ambiguity and delivers implementation evidence. CHO is accountable for wrong scope/delegation criteria; Harness is accountable for implementation defects against agreed criteria. CTO/CPO follow the same lead-versus-implementer split. The lead may not move unowned release obligations into a subordinate's code DoD. No reduction of independent reviewer independence. Record \`DOC_IMPACT\` and the specific canonical page updated. This policy supersedes historical advice to fix review loops by merely increasing \`maxReviewRounds\`.
