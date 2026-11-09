# Paperclip — agent-only review/rework routing (owner directive 2026-11-06)

## Scope and intent
The owner does not want routine technical issues silently handed to a human after three agent `changes_requested` decisions. Keep code review independent, preserve genuine approval and GitHub/deploy authorization, and let the executor/CTO/CHO finish the work without fake human decisions. This directive does not remove explicitly mandated human/legal/security approvals.

## Native, no-fork setting
When creating or revising an issue with agent review participants:
- Set `executionPolicy.maxReviewRounds: 50` explicitly in the authoritative native Paperclip issue policy at creation time; do not accept the upstream default of 3. 50 is a technical ceiling, **not** permission for 50 unproductive loops.
- Preserve every existing `executionPolicy.stages[]` stage ID, reviewer participant, approval count, `mode`, `commentRequired`, `reviewPolicy=not_creator`, blockers, ownership and workspace configuration. Assign independent CTO/CHO or an appropriate reviewer; never self-review.
- On each agent review `changes_requested`, retain native decision, return to the executor, require concrete before/after evidence, tests and exact PR head SHA, then re-request the independent review. The rejection itself never means `cancelled`, `done`, a human escalation, or approval.
- At 3 consecutive similar rejections, CHO must examine the precise repeat root cause, change implementation approach or assign an independent second opinion. Treat lack of progress as a technical blocker, not a prompt for human approval or fake success. Do not create duplicate tasks or automatic routines.
- For already escalated `currentParticipant.type=user` issues, use authorized native recovery or execution-policy update, preserving the original decision history; never fabricate `executionState` or impersonate a user.
- The release gate must still require authentic native approval bound to exact SHA, successful CI, signed/promoted image, Coolify readback and rollback availability. This directive cannot repair `decision_not_bound`, cannot bypass an explicit `human_only` policy and cannot relax board-level security controls.

## Validation
A successful correction demonstrates: authoritative `maxReviewRounds=50` readback; real agent review run and persisted native decision; legitimate return to executor on `changes_requested`; no routine auto-escalation to human at rounds 3 or 4; and no bypassed review or release gate. Note that Paperclip's default constant remains 3 if a new issue does not explicitly set this per-issue override.

## Existing migration on 2026-11-06
16/16 then-open issues were updated through native `paperclipManageIssueExecutionPolicy(operation=set_mode, mode=normal, maxReviewRounds=50)`; KOMAA-1594 and KOMAA-1615 first returned from a user-held review to their agents, with stage and decisions preserved. KOMAA-1615 subsequently received a real CTO native `approved` decision, while the PR merge/deploy still requires independent verification. KOMAA-1594 entered another genuine review/rework cycle.

## Owner constraints
Do not modify the upstream Paperclip Core solely to hide a human decision. Do not reactivate disabled periodic heartbeats, routines or watchdogs. If a guaranteed per-issue default for all future issues cannot be achieved in supported creation templates, propose an extremely narrow external creation-wrapper validation with tests, or a separately reviewed minimal upstream change; do not silently alter runtime code or production images.


## 2026-11-07 correction: DoD stability precedes review-round ceiling

The issue is not solved by maxReviewRounds=50. Before delegating a real engineering task, the CHO/CTO/CPO lead must commit a versioned, testable acceptance contract shared with the executor and independently evaluating reviewer; see \`wiki/concepts/definition-of-done.md\` (Pre-delegation DoD contract and reviewer agreement). Separate CODE/REVIEW/RELEASE/OUTCOME ownership, recognize real emergent security defects, and categorize rejections as CODE_DEFECT, EVIDENCE_MISSING, ACCEPTANCE_DRIFT, EXTERNAL_GATE, or REVIEW_ENGINE_FAILURE. A code reviewer cannot endlessly reject correct code because a separate release owner lacks production credentials. Same immutable candidate + identical rejection repeated twice => no third unchanged rework attempt; trigger bounded independent technical comparison. Do not translate native review engine failures or status drift into fake implementer blockers. Actual Paperclip enforcement needs source regressions + production issue-run test; policy and skill edits alone do not prove it.
