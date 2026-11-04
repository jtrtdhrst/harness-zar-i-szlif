import { readFileSync, writeFileSync, copyFileSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const PINNED_SOURCE = "1b4c803816e82b0265c8422e1a804327a7ed8c54";
if (process.env.PAPERCLIP_CORE_BASE_SHA !== PINNED_SOURCE) {
  throw new Error("Refusing to apply Core patch without the exact pinned 2026.1023.0 source revision");
}
const root = resolve(process.env.PAPERCLIP_CORE_SOURCE_ROOT ?? "/app");
const edits = [
  {
    "file": "server/src/services/issue-thread-interactions.ts",
    "before": "import { normalizeEscapedLineBreaks } from \"@paperclipai/shared/validators/text\";",
    "after": "import { assertNativeIssueQuestionGovernance } from \"./native-issue-question-governance.js\";\nimport { normalizeEscapedLineBreaks } from \"@paperclipai/shared/validators/text\";"
  },
  {
    "file": "server/src/services/issue-thread-interactions.ts",
    "before": "      const data = normalizeCreateInteractionInput(\n        createIssueThreadInteractionSchema.parse(input),\n      );",
    "after": "      const data = normalizeCreateInteractionInput(\n        createIssueThreadInteractionSchema.parse(input),\n      );\n      assertNativeIssueQuestionGovernance(data, actor.agentId ?? null);"
  },
  {
    "file": "server/src/services/issue-execution-policy.ts",
    "before": "      if (requestedStatus !== undefined && requestedStatus !== \"in_review\") {\n        patch.executionState = null;\n        return { patch };\n      }\n      // Assignee-only override:",
    "after": "      if (requestedStatus !== undefined && requestedStatus !== \"in_review\") {\n        // A Board override is not a first-class stage decision. Never make a\n        // terminal/status mutation that silently erases pending review state.\n        // Emergency dispositions use the native audited stalled-review path.\n        throw unprocessable(\"Pending review requires an independently recorded stage decision; Board status override is not a review verdict\");\n      }\n      // Assignee-only override:"
  },
  {
    "file": "server/src/services/issue-execution-policy.ts",
    "before": "      patch.executionState = null;\n      if (input.issue.status === \"in_review\") {\n        patch.status = \"in_progress\";\n      }\n      return { patch };\n    }\n\n    if (attemptedStageAdvance && !stageStateDrifted)",
    "after": "      throw unprocessable(\"Pending review cannot be dissolved by assigning a nonparticipant; choose an eligible stage reviewer\");\n    }\n\n    if (attemptedStageAdvance && !stageStateDrifted)"
  },
  {
    "file": "server/src/services/issues.ts",
    "before": "  normalizeIssueExecutionPolicy,\n} from \"./issue-execution-policy.js\";",
    "after": "  normalizeIssueExecutionPolicy,\n  parseIssueExecutionState,\n} from \"./issue-execution-policy.js\";"
  },
  {
    "file": "server/src/services/issues.ts",
    "before": "export function issueService(db: Db) {\n  const instanceSettings = instanceSettingsService(db);",
    "after": "export function issueService(db: Db) {\n  // Keep the review stage authoritative during a reviewer checkout. The old\n  // unconditional status=in_progress caused review_pending_status_drifted.\n  // The CAS-style SQL expression uses the same row as the UPDATE, avoiding a\n  // stale pre-read of the issue while an independent reviewer is being switched.\n  const reviewerAwareCheckoutStatusSql = (agentId: string) => sql<string>`\n    case\n      when ${issues.status} = 'in_review'\n        and ${issues.executionState}->>'status' = 'pending'\n        and ${issues.executionState}->'currentParticipant'->>'type' = 'agent'\n        and ${issues.executionState}->'currentParticipant'->>'agentId' = ${agentId}\n      then 'in_review'\n      else 'in_progress'\n    end\n  `;\n  const instanceSettings = instanceSettingsService(db);"
  },
  {
    "file": "server/src/services/issues.ts",
    "before": "          executionRunId: checkoutRunId,\n          status: \"in_progress\",\n          startedAt: now,",
    "after": "          executionRunId: checkoutRunId,\n          status: reviewerAwareCheckoutStatusSql(agentId),\n          startedAt: now,"
  },
  {
    "file": "server/src/services/issues.ts",
    "before": "            executionLockedAt: now,\n            status: \"in_progress\",\n            updatedAt: now,",
    "after": "            executionLockedAt: now,\n            status: reviewerAwareCheckoutStatusSql(agentId),\n            updatedAt: now,"
  },
  {
    "file": "server/src/services/issues.ts",
    "before": "      const loadCurrent = () =>\n        db\n          .select({\n            id: issues.id,\n            status: issues.status,\n            assigneeAgentId: issues.assigneeAgentId,",
    "after": "      const loadCurrent = () =>\n        db\n          .select({\n            id: issues.id,\n            status: issues.status,\n            executionState: issues.executionState,\n            assigneeAgentId: issues.assigneeAgentId,"
  },
  {
    "file": "server/src/services/issues.ts",
    "before": "      const resolveSameRunOwnership = (candidate: {\n        id: string;\n        status: string;\n        assigneeAgentId: string | null;",
    "after": "      const isPendingReviewerCheckout = (candidate: { status: string; executionState?: unknown }) => {\n        const state = parseIssueExecutionState(candidate.executionState);\n        return candidate.status === \"in_review\" && state?.status === \"pending\" &&\n          state.currentParticipant?.type === \"agent\" &&\n          state.currentParticipant.agentId === actorAgentId;\n      };\n      const resolveSameRunOwnership = (candidate: {\n        id: string;\n        status: string;\n        executionState?: unknown;\n        assigneeAgentId: string | null;"
  },
  {
    "file": "server/src/services/issues.ts",
    "before": "          candidate.status === \"in_progress\" &&\n          candidate.assigneeAgentId === actorAgentId &&\n          sameRunLock(candidate.checkoutRunId, actorRunId)",
    "after": "          (candidate.status === \"in_progress\" || isPendingReviewerCheckout(candidate)) &&\n          candidate.assigneeAgentId === actorAgentId &&\n          sameRunLock(candidate.checkoutRunId, actorRunId)"
  },
  {
    "file": "server/src/services/issues.ts",
    "before": "        const releaseStatus =\n          existing.status === \"in_progress\" ? \"todo\" : existing.status;",
    "after": "        const preservePendingReviewOwner = existing.status === \"in_review\" &&\n          parseIssueExecutionState(existing.executionState)?.status === \"pending\";\n        const releaseStatus =\n          existing.status === \"in_progress\" ? \"todo\" : existing.status;"
  },
  {
    "file": "server/src/services/issues.ts",
    "before": "            assigneeAgentId: isTerminal ? existing.assigneeAgentId : null,",
    "after": "            assigneeAgentId: isTerminal || preservePendingReviewOwner ? existing.assigneeAgentId : null,"
  },
  {
    "file": "server/src/services/issues.ts",
    "before": "        if (!receiptExisting) return null;\n        if (expectedExecutionPolicy !== undefined",
    "after": "        if (!receiptExisting) return null;\n        const originalReviewState = parseIssueExecutionState(existing.executionState);\n        const lockedReviewState = parseIssueExecutionState(receiptExisting.executionState);\n        if ((originalReviewState?.status === \"pending\" || lockedReviewState?.status === \"pending\") &&\n            (receiptExisting.status !== existing.status ||\n             receiptExisting.assigneeAgentId !== existing.assigneeAgentId ||\n             receiptExisting.assigneeUserId !== existing.assigneeUserId ||\n             !isDeepStrictEqual(receiptExisting.executionState ?? null, existing.executionState ?? null))) {\n          throw conflict(\"Review stage changed during issue mutation; re-read the current stage before deciding\", {\n            code: \"REVIEW_SNAPSHOT_STALE\",\n          });\n        }\n        if (expectedExecutionPolicy !== undefined"
  }
];
const pending = new Map();
for (const { file, before, after } of edits) {
  const path = join(root,file);
  const source = pending.has(path) ? pending.get(path) : readFileSync(path,"utf8");
  const count = source.split(before).length - 1;
  if (count !== 1) throw new Error(`CORE_PATCH_SOURCE_DRIFT: ${file} has ${count} exact matches for expected source anchor`);
  pending.set(path, source.replace(before,after));
}
for (const [path,source] of pending) writeFileSync(path,source,"utf8");
const targets = [
  ["native-issue-question-governance.ts","server/src/services/native-issue-question-governance.ts"],
  ["native-issue-question-governance.test.ts","server/src/services/native-issue-question-governance.test.ts"],
  ["native-core-review-guard.test.ts","server/src/__tests__/native-core-review-guard.test.ts"],
];
for (const [name,dest] of targets) {
  const sourcePath = join("/opt/paperclip-core-overrides",name);
  const destPath = join(root,dest);
  mkdirSync(dirname(destPath),{recursive:true});
  copyFileSync(sourcePath,destPath);
}
console.log(`CORE_PATCH_APPLIED source=${PINNED_SOURCE} files=${pending.size} unit_test_files=${targets.length}`);