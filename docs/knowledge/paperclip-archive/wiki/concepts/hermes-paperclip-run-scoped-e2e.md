## 2026-11-07 VERIFIED STATE OVERRIDE — PR #36 MERGED, CUTOVER NOT VERIFIED

The earlier sentence on this page describing Hermes integration PR #36 as unmerged is **historical and now stale**. GitHub confirmed [Harness PR #36](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/36) merged on **2026-11-06**, exact PR head `833c507fad5ebfc50c7c34637495694f53068ada`. That is a **source merge only**, NOT completion of `KOMAA-1512` (still `in_review`), real Wiki/Skills/Hindsight/Opik authorization, canary nor production 14/14 cutover. At the 2026-11-07 snapshot 13 agents use `opencode_local` and the one `hermes_gateway` Designer is `error`.

CHO and Harness Engineer must first read `wiki/concepts/owner-change-delivery-and-open-defects-20261107.md` and then recheck current GitHub HEAD, native Paperclip issue/reviewer/run and live Coolify build/image/run telemetry. Keep the source runbook on main as canonical architecture/acceptance specification but correct its stale as-of-2026-11-04 state before using it as current release evidence. Native review and real E2E remain gating.

# Hermes ↔ Paperclip: run-scoped MCP E2E
> **LOCAL CODE ARCHITECTURE (not an incident log):** Before assuming upstream Paperclip Core behavior, read `wiki/concepts/paperclip-local-architecture-upstream-delta.md` and its attached `paperclip-local-architecture` Skill. This lists actual deployed Core overlays vs source-only patches, separate Paperclip MCP/Hermes services and pinned upstream `master`/release provenance. See the Hermes runbook below for task-specific E2E.


**Status:** implementation source/security approved (H01 / KOMAA-1564 DONE), **production release NOT approved**. This page is a discovery pointer, **not** a separate runbook or a substitute for a first-class reviewer decision.

**Canonical version-controlled source, architecture, test and release/rollback runbook:**
https://github.com/miloszspyrka-code/harness-zar-i-szlif/blob/main/integrations/hermes-paperclip/OPERATIONS-STATUS.md

**MANDATORY AGENT READ POLICY (when assigned Hermes/Paperclip Gateway/MCP integration, security, trace, migration or release work):** Before making changes, read the canonical main runbook above (or approved Wiki-backed equivalent), confirm the exact live Paperclip issue/review + GitHub PR head + deployment evidence, and reference the document path in the task evidence. Do not inject the whole runbook into unrelated roles/tasks. If access fails, report the exact denied tool/action and do not silently substitute stale pilot notes. Documentation on main is NOT adapter-code merge or permission for a production cutover.

**Documentation-only publication:** [PR #50](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/50) merged to main as `dd3e934179114bcf81a295d46f849b992f62e9b7`. Candidate code remains unmerged.

**Integration PR:** https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/36

**Approved H01 source/security baseline (2026-11-04):**
- Paperclip source worktree commit `792598741832c31d91d74c8de9e787639944d13e`;
- exact PR code commit `d6a6f5455f9732b17ba00dc163c4c985ca9627ff`;
- `execute.ts` SHA-256 `977e6ecfc457c330b8bc59e020456ca3361aebe877b065d4878573cd3cae0578`;
- focused tests 114/114 source and 108/108 pinned image; source-only CTO approval.
- Never assume subsequent PR commits are documentation-only; compare latest GitHub HEAD, exact diff, CI and reviewed SHA before any promotion.

**Outstanding native work (authoritative status must be re-read):** `KOMAA-1512` (H02 integration), `KOMAA-1494` (H05 real Named MCP), `KOMAA-1496` (Hermes + Hindsight + Opik E2E), `KOMAA-1513` (GitHub App → immutable artifact), `KOMAA-1497` (CHO-approved Coolify release, canary, rollback and cohort rollout).

**Execution-state rule:** issue `in_progress` does not prove an active run or approval. Read `KOMAA-1512` first-class review state, actual run UUID and recovery record before acting. Historical scheduler snapshots (including `false_progress_no_issue_run`) may be obsolete. CHO owns native recovery; never force-wake, bypass review or report DONE from an issue status alone.

**Non-negotiable release gate:** A real Paperclip-issued, issue/run-bound credential must pass authorized Wiki/Skills and denied wrong-agent/run/expired/revoked calls; native Hindsight own-bank retain/readback and cross-bank denial; Hermes-native Opik same-run UUID; exact reviewed SHA/image digest and safe rollback. No prompt/log/trace token disclosure. Preserve current production agent settings until each cohort passes.

Full procedures, source baselines and evidence format are maintained **only** in the GitHub runbook above. Do not duplicate the runbook in this Wiki page; link to its latest reviewed revision.