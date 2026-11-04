import { describe, expect, it } from "vitest";
import { safeUndispatchedReviewHandoff } from "./execution-blocker.js";

const issueId = "6ae2ec2e-1ba2-409f-ad69-d537f7a1ef9f";
const agentId = "ada5390b-b87e-43f3-a250-3657811e7a0c";
const reviewerId = "ff703eba-3c3d-46f0-b265-df0db1101a19";
const baseRun = {
  agentId, status: "cancelled", errorCode: "issue_reassigned",
  scopeKind: "issue", contextSnapshot: { issueId }, runtimeModeResolvedAt: null,
  processPid: null, processGroupId: null, processStartedAt: null,
  externalRunId: null, runnerInstanceId: null, nativeSessionId: null,
  driverKind: null, logBytes: null,
  resultJson: { reassignmentStopConfirmed: true, reassignmentStopRequested: true },
};
const base = {
  actionStatus: "resolved",
  actionCause: "legacy_execution_requires_reconciliation",
  noReplayMarker: "blocked", issueStatus: "in_review",
  currentAssigneeAgentId: reviewerId, sourceIssueId: issueId,
  run: baseRun,
};

describe("retired pre-dispatch reviewer recovery hold", () => {
  it("does not block a proven undispached old executor after a reviewer handoff", () => {
    expect(safeUndispatchedReviewHandoff(base)).toBe(true);
  });
  it("does not suppress active or unresolved recovery", () => {
    expect(safeUndispatchedReviewHandoff({ ...base, actionStatus: "active" })).toBe(false);
    expect(safeUndispatchedReviewHandoff({ ...base, noReplayMarker: undefined })).toBe(false);
  });
  it("requires actual independent reviewer and in_review state", () => {
    expect(safeUndispatchedReviewHandoff({ ...base, currentAssigneeAgentId: agentId })).toBe(false);
    expect(safeUndispatchedReviewHandoff({ ...base, issueStatus: "todo" })).toBe(false);
    expect(safeUndispatchedReviewHandoff({ ...base, issueStatus: "done" })).toBe(false);
  });
  it("never suppresses a provider run with any dispatch marker or uncertain stop", () => {
    for(const patch of [
      { runtimeModeResolvedAt: new Date() }, { processPid: 11111 }, { processGroupId: 22222 },
      { processStartedAt: new Date() }, { externalRunId: "external" }, { runnerInstanceId: "v1" },
      { nativeSessionId: "v2" }, { driverKind: "remote" }, { logBytes: BigInt(1) },
      { resultJson: { reassignmentStopConfirmed: false } }, { status: "running" },
      { errorCode: "model_error" }, { scopeKind: "conversation" },
      { contextSnapshot: { issueId: "other-issue" } },
    ]) {
      expect(safeUndispatchedReviewHandoff({ ...base, run: { ...baseRun, ...patch } })).toBe(false);
    }
  });
});
