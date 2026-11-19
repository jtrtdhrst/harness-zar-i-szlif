---
title: Owner changes — CHO / Harness Engineer execution contract and open defects (2026-11-07)
type: concept
tags: [owner-directive, cho, harness, e2e, release, github, security, hermes, paperclip]
updated: 2026-11-07
---

# Owner changes: authoritative execution handoff for CHO and Harness Engineer

**Audience:** CHO (owner of reliable delegated execution, independent Harness review, closure) and Harness Engineer (implementation, diagnosis, source/tests/readback). **Language:** English for issues, logs, infrastructure and runbooks. Polish remains the language of end-user product copy.

**This is a durable OWNER-INTENT and OPEN-DEFECT handoff, not a claim that the defects are repaired.** Evidence snapshot checked on 2026-11-07 against Paperclip, GitHub, Coolify and Ubuntu. Recheck live state before changing anything. This page supplements, but does not override, repository-local architecture, the canonical [two-repository release contract](wiki/concepts/git-coolify-release-contract.md), [agent git policy](wiki/concepts/agent-git-delivery-policy.md), [Hermes run-scoped E2E pointer](wiki/concepts/hermes-paperclip-run-scoped-e2e.md), native issue policies, and actual review/security gates. When an older statement conflicts with a newly verified immutable artifact, reconcile and update the stale source; do not silently follow it.

## Owner intent: what success means

1. **Execute, not audit-loop.** Fresh state → reproduce the failing case → minimal root-cause patch → focused and negative regression → independent first-class exact-SHA review → authorized integration → per-service build/deploy (canary when relevant) → authenticated production readback + rollback/forward proof → native DONE. Merely drafting instructions, comments, a new issue, green generic CI or changing issue status is NOT completion.
2. **No process theater.** Prefer the existing canonical issue and its branch/PR, not duplicate tasks, serial reviewers, generic approval questions, rescheduling loops, or artificial human gates. Never bypass real authorization, source ownership, independent review, OAuth consent or production safety.
3. **Protect GitHub account and Actions budget.** No Paperclip agent, Harness or automation may comment, react, open an issue/PR, push, review or otherwise write to `paperclipai/paperclip` or another third-party public repository on the owner's behalf without explicit scoped owner authorization. Access to read upstream is allowed. Treat any observed unsolicited external write as a security incident: preserve evidence, revoke/restrict the actual credential route and verify denial with an appropriately bounded negative test. Scope GitHub App installations and per-run permissions to explicitly owned repositories; do not replace with a broad PAT. Do NOT claim isolation is proven from an instruction alone.
4. **Minimize CI cost.** The owner reported ~90% monthly GitHub Actions budget consumed as of 2026-11-07. No heartbeat-triggered push, redundant branch/PR, empty commit, docs-only rebuild storm, automatic retry or test loop without new source/evidence. One meaningful candidate, one push/PR per actual unit, target-aware local tests before CI, conditional workflows/path filters/concurrency cancellation after review. Preserve mandatory security/release checks; do not disable them merely to reduce usage. Measure actual workflow run counts/minutes and triggering actors before claiming savings.
5. **One correct source of truth.** `miloszspyrka-code/zar-i-szlif` owns the product app, website, product MCP; `miloszspyrka-code/harness-zar-i-szlif` owns general MCP, Harness, Paperclip/Hermes integration and host release controllers. Never write/merge into upstream `paperclipai/paperclip`. Existing three approved Cloudflare Workers remain; deploy other apps/services through their actual Coolify lanes. Do NOT impose universal `main` as production branch: product uses `ci-approved`; each Harness service has its own immutable promotion/ref/digest policy.
6. **Evidence follows every owner change.** Document the reason, current behavior, target behavior, owner/reviewer, files/repos/service UUIDs, risk/rollback, test commands and results, PR HEAD and reviewed HEAD, merge SHA, image digest, deployment ID, authenticated negative/positive probes, production readback and residual blockers. Append a short `DOC_IMPACT: updated | not-applicable (reason)` field to the existing issue; update canonical runbook when architecture/runtime/behavior changes. Do not paste credentials, token URLs, private payloads or PII.
7. **Do not misreport DONE.** When access, native approval, or real E2E is missing, describe precise unsatisfied gate and the next executable owner action. Do not claim a document, successful tool call, healthy container or merged PR is a full production fix.

## Responsibilities (no duplicate reviewer queue)

| Decision | CHO | Harness Engineer |
| --- | --- | --- |
| Select existing issue, unblock native DAG, delegate/route | Accountable | Supply concrete failure/root cause and useful next action |
| Infrastructure/Paperclip/Hermes code & regression | Independent native reviewer (cannot self-review) | Implementer, owns isolated workspace and exact candidate SHA |
| Native PR lineage and review recovery | Proves actual persisted decision, correct assignee/run, can authorize further lane | Reproduce real state transitions; repair minimal authorized code, supply negative regression |
| GitHub rights, external write, CI minutes | Enforce repo allowlist, cost & risk acceptance | Locate actor/credential/workflow trigger; implement least-privilege and path-aware fix |
| Production release & final closure | Release acceptance, deployment/rollback/readback, status DONE only with proof | Execute scoped canary, tests, deploy verification and report evidence |
| Product code review in product repo | Not default second reviewer | Not default implementer; product Engineer implements and CTO independently reviews |

One independent code review per actual delivery unit: **Harness → CHO; Product → CTO**. Any additional security/human review needs a specific justified high-risk boundary, not an automatic second queue. Preserve `executionPolicy`, `blockedBy/blocks`, reviewer identity and first-class decisions; a comment does not satisfy a native approval.

## Verified 2026-11-07: fixed source changes vs open E2E

**Merged source — NOT automatically deployed or E2E:**
- Harness [PR #36](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/36) Hermes receiver/adapter — **merged 2026-11-06**, head `833c507fad5ebfc50c7c34637495694f53068ada`. Older Wiki/runbook prose saying it remains open is STALE.
- Harness [PR #57](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/57) independent reviewer checkout — merged 2026-11-06.
- Harness [PR #48](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/48) H03 reconciliation — merged 2026-11-06.
- Harness [PR #62](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/62) CI release-folder test — merged 2026-11-06.
- Product [PR #157](https://github.com/miloszspyrka-code/zar-i-szlif/pull/157) path-specific CI — merged 2026-11-06; [PR #158](https://github.com/miloszspyrka-code/zar-i-szlif/pull/158) injected Coolify compose build fix — merged 2026-11-06.
- Harness [PR #33](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/33) PR-head linkage regression and [PR #61](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/61) documentation preflight enforcement — still OPEN at the snapshot.
- Historical PR #34 closed **without** merge; do not use it as deployed evidence.

**Open native task gates (read these first):**
- `KOMAA-1512` Hermes run-scoped bridge `in_review` (no active run at readback); `KOMAA-1494` Wiki/Skills and `KOMAA-1496` end-to-end Hindsight/Opik `blocked`.
- `KOMAA-1513` GitHub App → Coolify real agent run and `KOMAA-1497` exact-SHA Hermes release/canary/rollback `blocked`.
- `KOMAA-1559` PR work-product SHA/rework regression `in_review` (PR #33 still open).
- `KOMAA-1594` native review → rework recovery `in_progress`, but no active run at snapshot.
- `KOMAA-1605` Opik OAuth/telemetry E2E `blocked`; `KOMAA-1553` Hindsight isolation migration `blocked`.
- `KOMAA-1595` reviewer false-progress fix `done`. Do not confuse partial source fix with passing the larger live E2E.
- `KOMAA-1616` (product all-path CI), `KOMAA-1617` (Harness CI) and `KOMAA-1628` (Coolify build repair) marked `done`. Validate exact current production SHA per service independently.

**Actual agent runtime:** Paperclip lists **14 agents**. Designer alone is configured `hermes_gateway` with status `error`; other **13 are `opencode_local`**. No completed 14/14 Hermes rollout. Do not flip entire cohort before a real authorized issue-scoped probe: positive Wiki/Skills, deny wrong-agent/run/expired access, own Hindsight bank retain/readback, cross-bank denial, same-run Hermes Opik trace, rollback proof. When canary fails, restore a known-working agent and record failure.

**Coolify on 2026-11-07:** healthy core services include `zar-i-szlif-web`, Hermes production/candidates, Paperclip Core/MCP, Hindsight and Opik; yet stale `hermes-gateway-poc` is `exited:unhealthy`, `hermes-permissions-repair-temporary` and `ubuntu-mcp-oauth-proxy` are `exited`, and `mcp-activation` is `running:unknown` without working healthcheck. Establish whether each is intentionally retired before deleting/restarting; no duplicate new service. On host three systemd units are failed: `hermes-cpo-readiness.service`, `hermes-profile-skills-sync.service`, `paperclip-mcp-auto-release.service`. A timer being enabled is not proof its service succeeded. VPS showed ~75% disk usage, 11/15 GiB swap occupied; profile resources before builds.

## Root-cause acceptance matrix: P27–P38 follow-up

The historical `/root/P27-P38-debug-plan-20261106.md` was **not found** at that location on 2026-11-07. Do not fabricate its complete contents. Validate original issue evidence and use this matrix as a scoped hypothesis list, not proof all defects persist:

| Area | Required verified outcome |
| --- | --- |
| P27 — PR merge writeback | Actual `paperclipGitMergePR` persists `acceptedHeadSha`, decision ID, `mergeCommitSha`, and `merged` status linked to the **same** work product; replay/stale SHA denied |
| P28–29 — preflight/Board bypass | Repo DOC_PREFLIGHT admission and Board/agent API paths actually enforce same source/trust boundary; canary no-op and bypass tests must fail closed |
| P30–32 — source/manifest provenance | Exact resource → repo/path → ref → source SHA → image digest → running instance, including image-only/Compose services; reconcile older docs |
| P33–34 — release/cleanup | Per-service canary, rollback/forward proof; identify retired POCs and remove only after dependency and data checks |
| P35 — GitHub branch protection | Read actual server-side required-PR/review/check rules for BOTH private repos; tool policy or protected=false must not be called full protection |
| P36 — native lineage/review | Real issue-bound reviewer run and decision on exact SHA; GitHub merge/writeback; deployment identity; no status-only DONE |
| P37 — VPS resources | Resource-aware build scheduling, stop redundant builds, monitor RAM/swap/disk/IO from real data; don't starve Paperclip concurrency |
| P38 — Hermes cohort | 14/14 agents on authenticated and verified Hermes only after individually/canary validated; Designer error must be resolved first |

## Mandatory workflow for every new owner-directed change

- **Start:** identify existing canonical issue/branch/PR; read minimal role instruction, the matching Wiki, repository README/AGENTS and affected service documentation. `DOC_PREFLIGHT` records doc paths/revisions/source SHA, owner, scope and STOP/PASS. Do not read every document for a small task.
- **Preflight:** actual Paperclip issue/assignee/run/reviewer/dependencies; GitHub HEAD & required checks; Coolify service UUID, git ref or image digest and latest deployment; host logs/resources; Opik/Hindsight correlation only if relevant. Distinguish facts, historical observation, uncertainty.
- **Change:** one issue-owned worktree, no direct `main`, no upstream public writes, no broad PAT, no duplicate agent issue or speculative PR; write tests against the reproduced failure and expected denial. Correct architecture/manifest/runbook within the same candidate before review.
- **Review:** one independent first-class reviewer for the right repo, bound to exact tested SHA; read back review decision and artifact lineage. Reject stale approval/unknown reviewer.
- **Release:** immutable reviewed integrated source → target-specific authorized release lane → real build → image digest/deployment ID → authenticated smoke and health → rollback and forward. Any missing gate stays OPEN/UNVERIFIED.
- **Close:** evidence link to original task; add `DOC_IMPACT` decision, updated canonical architecture/service/runbook and corrected stale pointers, residual risks and the next real blocker. Never claim DONE from a note or healthy container.

## Fast handoff — what to do next

**CHO:** first check `KOMAA-1594` native recovery and `KOMAA-1559` exact SHA/merge writeback; compare the current first-class issue/PR stage to real executions. Enforce upstream deny + Actions consumption investigation as an immediate security/cost priority using the existing incident/work, not a duplicate vague ticket. Accept only tested, reviewed source and real release evidence.

**Harness Engineer:** reproduce the faulty merge metadata on the current version and implement the narrow writeback regression; verify DOC_PREFLIGHT enforcement including Board path; repair Hermes Designer canary `error` and the real run-scoped MCP grant path; diagnose failing systemd services only after identifying their active owner/release lane. Supply exact failure fingerprint, version/diff/tests, negative auth control, candidate SHA, readback and rollback. Do not execute unrelated speculative repairs.

**Live state wins:** all dates and states above are a point-in-time snapshot on **2026-11-07**, not an automation, monitoring promise or permission to skip current verification.
