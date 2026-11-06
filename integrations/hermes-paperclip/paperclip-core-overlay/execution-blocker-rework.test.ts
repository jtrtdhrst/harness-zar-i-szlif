import { describe, expect, it } from "vitest";
import { safeAbortedLegacyReworkHandoff as safe } from "./execution-blocker.js";

const issueId = "8950daaf-32cd-4ce5-b2f1-c76833400f14";
const oldAgentId = "ada5390b-b87e-43f3-a250-3657811e7a0c";
const newOwnerId = "5595f2c4-95e2-4c3e-97b4-c00d4e4d6601";
const baseRun = {
  agentId: oldAgentId, status: "cancelled",
  errorCode: "legacy_disposition_repair_suppressed",
  scopeKind: "issue", contextSnapshot: { issueId },
  runtimeModeResolvedAt: new Date("2026-11-04T13:17:25.740Z"),
  processPid: null, processGroupId: null, processStartedAt: null,
  externalRunId: null, runnerInstanceId: null, nativeSessionId: null,
  driverKind: null, logBytes: null,
  resultJson: { cancellation: {
    reason: "Execution stopped without a recorded cancellation request: Disposition repair suppressed: recorded_disposition",
    source: "unknown", expected: false
  } }
};
const base = {
  actionStatus: "resolved", actionCause: "legacy_execution_requires_reconciliation",
  noReplayMarker: "blocked", issueStatus: "todo",
  currentAssigneeAgentId: newOwnerId, sourceIssueId: issueId,
  executionState: { status: "changes_requested", lastDecisionId: "bb6d7266-5106-4330-b014-9ddfbbf00447",
    lastDecisionOutcome: "changes_requested",
    returnAssignee: { type: "agent", agentId: newOwnerId } },
  run: baseRun
};
describe("resolved legacy pre-process rework hold", () => {
  it("allows a new, typed rework round after proven aborted legacy dispatch", () => {
    expect(safe(base)).toBe(true);
    expect(safe({ ...base, issueStatus: "in_progress" })).toBe(true);
  });
  it("fails closed without the exact resolved no-replay record", () => {
    for (const change of [
      { actionStatus: "active" }, { actionStatus: "escalated" },
      { actionCause: "other" }, { noReplayMarker: "allowed" },
      { issueStatus: "in_review" }, { issueStatus: "blocked" },
      { issueStatus: "done" }, { issueStatus: "cancelled" },
      { currentAssigneeAgentId: oldAgentId }, { sourceIssueId: "other-issue" },
      { executionState: null },
      { executionState: { ...base.executionState, status: "pending" } },
      { executionState: { ...base.executionState, lastDecisionId: null } },
      { executionState: { ...base.executionState, lastDecisionOutcome: "approved" } },
      { executionState: { ...base.executionState, returnAssignee: { type: "agent", agentId: oldAgentId } } }
    ]) expect(safe({ ...base, ...change })).toBe(false);
  });
  it("fails closed if ANY sign of work dispatch or changed cancellation evidence appears", () => {
    const markerChanges = [
      { processPid: 1234 }, { processGroupId: 1234 },
      { processStartedAt: new Date() }, { externalRunId: "remote" },
      { runnerInstanceId: "runner" }, { nativeSessionId: "sess" },
      { driverKind: "remote" }, { logBytes: 1 }, { runtimeModeResolvedAt: null },
      { status: "running" }, { status: "failed" }, { errorCode: "other" },
      { scopeKind: "company" }, { contextSnapshot: { issueId: "different" } },
      { agentId: newOwnerId }, { resultJson: null },
      { resultJson: { cancellation: { reason: "unknown" } } }
    ];
    for (const change of markerChanges) expect(safe({ ...base, run: { ...baseRun, ...change } })).toBe(false);
  });
});
