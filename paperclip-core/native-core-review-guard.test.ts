import { describe, expect, it } from "vitest";
import {
  normalizeIssueExecutionPolicy,
  applyIssueExecutionPolicyTransition,
} from "../services/issue-execution-policy.js";

const EXECUTOR = "11111111-1111-4111-8111-111111111111";
const REVIEWER = "22222222-2222-4222-8222-222222222222";
const BOARD = "board-user";
function pendingIssue() {
  const policy = normalizeIssueExecutionPolicy({
    mode: "normal",
    maxReviewRounds: 12,
    stages: [{ type: "review", participants: [{ type: "agent", agentId: REVIEWER }] }],
  })!;
  return {
    policy,
    issue: {
      status: "in_review",
      assigneeAgentId: REVIEWER,
      assigneeUserId: null,
      responsibleUserId: BOARD,
      executionPolicy: policy,
      executionState: {
        status: "pending",
        currentStageId: policy.stages[0].id,
        currentStageIndex: 0,
        currentStageType: "review",
        currentParticipant: { type: "agent", agentId: REVIEWER },
        returnAssignee: { type: "agent", agentId: EXECUTOR },
        completedStageIds: [],
        lastDecisionId: null,
        lastDecisionOutcome: null,
        changesRequestedCount: 0,
      },
    },
  };
}
describe("Core review decisions stay first class", () => {
  it("denies status=done and status=in_progress from a foreign Board actor", () => {
    for (const status of ["done", "in_progress", "cancelled"] as const) {
      const { issue, policy } = pendingIssue();
      expect(() => applyIssueExecutionPolicyTransition({
        issue,
        policy,
        requestedStatus: status,
        requestedAssigneePatch: {},
        allowBoardOverride: true,
        actor: { userId: BOARD },
        commentBody: "Attempt to bypass the reviewer",
      })).toThrow("Pending review requires an independently recorded stage decision");
    }
  });
  it("does not dissolve review by assigning a nonparticipant", () => {
    const { issue, policy } = pendingIssue();
    expect(() => applyIssueExecutionPolicyTransition({
      issue,
      policy,
      requestedAssigneePatch: { assigneeAgentId: EXECUTOR },
      allowBoardOverride: true,
      actor: { userId: BOARD },
    })).toThrow("Pending review cannot be dissolved");
  });
  it("keeps the active independent reviewer free to approve atomically", () => {
    const { issue, policy } = pendingIssue();
    const r = applyIssueExecutionPolicyTransition({
      issue, policy, requestedStatus: "done", requestedAssigneePatch: {},
      actor: { agentId: REVIEWER }, commentBody: "Reviewed the exact candidate SHA",
    });
    expect(r.decision).toMatchObject({ outcome: "approved" });
    expect(r.patch.executionState).toMatchObject({ status: "completed" });
  });
  it("keeps actionable changes_requested on the original executor", () => {
    const { issue, policy } = pendingIssue();
    const r = applyIssueExecutionPolicyTransition({
      issue, policy, requestedStatus: "in_progress", requestedAssigneePatch: {},
      actor: { agentId: REVIEWER }, commentBody: "Fix stale SHA regression",
    });
    expect(r.decision).toMatchObject({ outcome: "changes_requested" });
    expect(r.patch.assigneeAgentId).toBe(EXECUTOR);
    expect(r.patch.executionState).toMatchObject({ status: "changes_requested" });
  });
});
