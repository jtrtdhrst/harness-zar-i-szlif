---
title: Agent Git Delivery Policy — canonical branch, commit, push and release
type: concept
tags: [git, branch, delivery, agents, review, governance]
updated: 2026-10-15
---

# Agent Git Delivery Policy (v1)
Scope: repositories owned by the company. This is the ONE canonical policy for agents performing REPO_WRITE. It complements [Definition of Done](wiki/concepts/definition-of-done.md) and repo-specific gates in AGENTS.md. A wiki rule is not a substitute for GitHub protection, native Paperclip eligibility, or CI enforcement.

## Deterministic branch admission
- ONE independently accepted outcome/root canonical Paperclip issue -> ONE short-lived branch, ONE issue execution workspace, and normally ONE PR. New tool run, review request, docs work, retry, error fingerprint, deployment, or specialist handoff NEVER creates a new branch.
- Branch is created ONLY at the first necessary repo mutation; read-only diagnosis, documentation decisions and admin run create ZERO branches.
- Reuse existing issue branch on all resumes and CHANGES, if recoverable and correct. Prefer exactly `KOMAA-<number>` matching canonical source issue; emergency only `hotfix/KOMAA-<number>` for a confirmed production incident with its own independent outcome. Neither freeform `-retry`, `-review`, `-deploy`, nor separate branch per agent.
- A genuine different deliverable with independently testable acceptance can receive its own canonical issue/branch only after Definition of Worth, unique scope and authorized issue creation. No mechanical "one branch per role" split.
- BEFORE provisioning, inspect the source issue, existing workspace/branch, open PRs and exact path ownership. Fail closed if a second active branch already owns the same issue/outcome. Existing legacy branches and PRs are INVENTORIED then migrated/closed only after evidence; NEVER mass delete/reset them or break current in-flight delivery blindly.
- Start from fetched and verified current `origin/main` (Paperclip source repo uses `origin/master`). Record immutable `base_sha`, `workspace_id`, branch and issue ID. Stale worktree containing accepted/dirty work: preserve it; single authorized reconcile/port commits to fresh current base, prove no lost changes, rerun affected tests. Do not create a new branch as a retry shortcut.
- ONE active code-writing lane per agent; ONE writer per file/artifact at a time. Parallel work is allowed for truly independent files/worktrees. Reviewer is read-only on executor candidate; fixes go back to original writer.

## Commit admission
- Commit when a COHERENT, reviewable acceptance slice is complete and narrow targeted verification passes. Multiple tool invocations/edit cycles inside one slice -> ONE commit; do not commit after every file edit/heartbeat. Keep all needed related tests and code together. Avoid unrelated opportunistic refactors.
- Normally 1 logical commit per deliverable. Multiple commits allowed only for materially separate testable steps, explicit safe checkpoints before lengthy or risky work, or reviewer-requested corrections. Never fabricate commits to show activity. No numeric arbitrary daily quota.
- Conventional message `feat(KOMAA-123): observable outcome`, `fix(KOMAA-123): causal bug`, `test(KOMAA-123): regression`, `docs(KOMAA-123): canonical contract` or `chore(KOMAA-123): tooling`; prefix ID must match owned canonical branch. NO synthetic git authorship. No committing secrets, generated clutter or irrelevant artifacts. Worktree must be clean before push.
- Maintain exact `candidate_sha`; verification and formal review bind to that SHA, never to movable HEAD or a textual PASS. Any post-review commit invalidates affected verification/approval, so re-run/review on new candidate.

## Push and PR admission
- Initial push occurs ONLY after meaningful candidate exists, required target-aware local gates PASS, and worktree is clean. Then ONE PR from canonical branch to base. No push per run/heartbeat, no speculative/draft spam, no duplicate PR for the same issue/accepted outcome.
- Additional pushes ONLY for explicit review CHANGES, validated failure fixes, real scope delta, or necessary rebasing; each time record new SHA and invalidate stale review. When a branch has no new change, ZERO push and ZERO new PR. Never push directly to main/master; never force push, silently rebase under a live review, or use --no-verify as workaround.
- Review requires named independent participant + formal persisted decision. CTO selects exact accepted SHA. Integrator only transports that authorization (one GitHub write authority). No auto-merge on successful agent run alone.
- Merge through authorized PR/fast-forward where candidate SHA is provably preserved in `origin/main` ancestry; otherwise require explicit mapped reviewed-tree equivalence, with fresh checks and authority. Default prefer ancestry-preserving merge, not squash that loses exact candidate SHA.
- Release runs from exact integrated main SHA with relevant target-specific preflight, production smoke, rollback and live readback. `done` only after applicable acceptance + `DOC_IMPACT` evidence. A PR/commit/green local build is NOT production delivery.
- After durable integrated candidate, no open dependent work/review/run and exact branch/commit lineage is recoverable, safely delete remote/local feature branch and archive worktree. If unmerged/dirty/behind/uncertain -> no destructive cleanup.

## Machine-state transitions (first matching)
- DUPLICATE_OUTCOME -> reuse root; no task, branch, commit, PR or extra run.
- NO_REPO_CHANGE -> no Git branch.
- EXISTING_ISSUE_BRANCH -> reuse; never fork on resume.
- DIRTY_OR_UNMERGED -> preserve, request authorized reconcile; never reset/delete.
- MISSING_REAL_DEPENDENCY, HUMAN/BOARD/REVIEW, PROVIDER/TOOLING HOLD -> no push/retry; exact owner, gate and event.
- READY + NO_BRANCH -> provision one isolated issue branch/worktree.
- VERIFIED_CANDIDATE -> push once, create/update canonical PR, request real review.
- CHANGES -> same branch, targeted patch/test, updated SHA, explicit re-review.
- APPROVED_EXACT_SHA -> CTO authorized merge once.
- INTEGRATED -> target deploy and live validation where applicable.
- DONE + RECOVERABLE -> safe branch/worktree cleanup.

## Explicit enforcement layers
1. GitHub: protected main/default branch, require PR, required CI, ≥1 independent review, dismiss stale approvals, no force push/deletion, constrain bypass and push rights.
2. Git hook/pre-push and CI: validate branch naming/issue ownership, commit metadata, changes versus base, target-specific checks, and prohibit bypass. Rules apply at server too; hooks alone are not controls.
3. Paperclip native code/control-plane: unique issue/workspace branch lease, serialized writer ownership, preflight no duplicate active branch, typed review + exact SHA + approval lineage, integration and cleanup gates. Must be RED→GREEN tested and independently deployed before being called fully enforced; do not claim prompt-only policy is native enforcement.
4. Agent skills: only how to comply; NEVER used as sole enforcement.

## Verification fixtures
- Two agents retry same canonical issue -> same branch, no second PR.
- Review CHANGES -> same branch, new SHA + invalidated old PASS.
- Read-only task -> zero branches.
- Different independently accepted concurrent issues -> two isolated branches; same file ownership -> serialize writes.
- Two branch names containing same canonical issue => second new branch push refused.
- Branch push with absent issue ID, wrong ID/author, synthetic identity, dirty tree or no gate -> fail closed.
- Unmerged/dirty candidate or active dependent -> cleanup denied.
- Reviewer=creator, stale SHA, CI missing/failed, unauthorized integration, unverified production => done/merge denied.
- Existing legacy PRs inventoried rather than deleted in bulk.

## Operational observability
Track unique accepted LIVE outcomes, branches opened per unique delivered issue, active branch age, duplicate branch attempts rejected, orphan worktrees, commits/pushes per accepted outcome, reviewer latency, stale candidate SHA, unmerged candidate count. Counts are diagnostic not quotas or incentives; do not block a legitimate second independent deliverable to meet an arbitrary global branch cap.

## Git transport RACI — verified effective agent permissions (2026-10-15)
- Engineer, MCP Engineer and Harness have explicit OpenCode `git *push*` DENY and `gh *` DENY. Therefore they MAY create tested candidate commits locally, but MUST NOT attempt direct remote push, GH API/curl or second credential workaround. Agent reports candidate SHA/branch/workspace/evidence; authorized CTO/Git Integrator performs the SAME BRANCH initial push and PR after fresh immutable-gate readback. This is transport, never authorship or self-review.
- CTO's effective OpenCode configuration currently permits `git push`/gh, while raw `api.github.com` bash paths are denied; actual write permission and authentication require independent preflight. Only one authorized GitHub writer per PR; no forced fallback when denial occurs.
- The practical chain for routine product work is: Engineer local candidate + test -> CTO/integrator publishes exact issue branch -> independent review on exact SHA -> CTO merge authorization -> integrator merge -> release owner verifies live. If CTO authors any source candidate, CTO MUST NOT self-review; route independent named reviewer.
- GitHub-hosted PR CI gates are only active on default branch AFTER an authorized merge of PR #45. The connected GitHub surface cannot currently perform admin ruleset/branch-protection writes; require a separately verified Board/admin execution and readback. Until then, pre-push+CI are defense-in-depth, not server-enforced branch protection.


## MCP engineer owner-bound repository/path admission v69 (2026-10-20)
Current `origin/main` includes `app/mcp-worker` at merged `a8b251bb...`, but KOMAA-1003 `HEAD=13d9b6a9...` is two commits ahead/one behind and lacks that module. The correct fix is SAME-branch ancestry-preserving reconciliation retaining its security changes and open CTO review, never reset/force push or editing the legacy Worker. Validate remote+tree at source commit AND compare changed paths before edit/commit and review. Run negative tests for denied out-of-scope paths across effective edit/shell/MCP workspace-writing tools; until an enforcing source permission/CI check is verified, mark `PATH_GUARD=POLICY_ONLY` and do not claim hard enforcement.

## Coolify release branches and artifacts (2026-11-05)
Read [GitHub → Paperclip → Coolify — canonical two-repository release lanes](wiki/concepts/git-coolify-release-contract.md) before any build, merge or deployment in either repository. It lists the verified Coolify git_branch vs immutable-image services, exactly one release writer per service, required independent native review, final source SHA, production readback, rollback, and current blockers. This does NOT override the mandatory controls above or permit an unreviewed deployment.


## Mandatory repository-documentation preflight (2026-11-05)
At first repository retrieval over GitHub MCP or a task workspace, read the exact repository's root README and AGENTS.md if present; verify target repo/paths against `harness-zar-i-szlif/README.md` ownership map. Before any repository write, also load the **targeted** canonical architecture/release/service documentation applicable to that issue: `docs/COOLIFY-PROJECTS.md`, `docs/RELEASE-POLICY.md`, `ops/release-lanes.json`, and an affected service runbook. For product work read product README and relevant product docs; for Paperclip upstream read its AGENTS.md and declared mandatory doc files. Avoid loading unrelated docs. Reuse verified doc SHA during one run.

Record per issue, before first write, a compact `DOC_PREFLIGHT` checkpoint with `issue/run/agent/repo/baseSha/readDocs[path+blobSha]/targetPaths/ownership/releaseLane/conflicts/decision`; never claim to have read files without a real read and verifiable SHA. On conflict with current live source/deployment, preserve source and check live Coolify/Ubuntu and PR state. Stop write if owner, scope or deploy lane cannot be established. Missing optional docs are marked `MISSING` and handled via README, targeted Wiki and live evidence rather than speculative reconstruction. An existing issue resumes the same branch and does not create a documentation subtask automatically.

This is a **behavioral gate**, not yet a native hard gate: GitHub rules/CI and Paperclip API must independently reject missing or forged preflight before hard enforcement can be claimed. Required negative E2E tests: wrong repo, wrong path, absent run scope, stale doc vs active deployment, absent release authorization and independent-review mismatch. No automatic deploy based solely on merge; preserve per-service release policy. The mandatory attached Paperclip company skill `agent-git-delivery` carries the short operational procedure.
