import { describe, expect, it } from "vitest";
import { assertNativeIssueQuestionGovernance } from "./native-issue-question-governance.js";

const AGENT = "11111111-1111-4111-8111-111111111111";
const form = (title: string, prompt: string, labels: string[]) => ({
  kind: "ask_user_questions",
  title,
  payload: { version: 1, questions: [
    { id: "path", prompt, selectionMode: "single",
      options: labels.map((label, i) => ({ id: String(i), label })) },
  ] },
});
describe("Core direct API technical-question governance", () => {
  it("denies the native KOMAA-1553 admin bearer / SSH form", () => {
    expect(() => assertNativeIssueQuestionGovernance(
      form("Which Hindsight/Hermes access path?", "Which unblock path?", [
        "Re-issue ssh_execute sudo grant", "Provide a Hindsight admin bearer",
      ]), AGENT,
    )).toThrow("Agent technical or credential escalation");
  });
  it("denies the KOMAA-1585 repository authorization form", () => {
    expect(() => assertNativeIssueQuestionGovernance(
      form("Authorize PR #40 source scope", "Which path should I follow?", [
        "Authorize read-only worktree", "Reassign source path",
      ]), AGENT,
    )).toThrow("Agent technical or credential escalation");
  });
  it("does not let the creator escape by renaming the form or hiding the request in options", () => {
    expect(() => assertNativeIssueQuestionGovernance(
      form("One quick question", "Choose your preference", [
        "Provide the production API key to the agent", "Maybe later",
      ]), AGENT,
    )).toThrow("Agent technical or credential escalation");
  });
  it("blocks technical access requests disguised as ordinary confirmations", () => {
    for (const kind of ["request_confirmation", "request_checkbox_confirmation"]) {
      expect(() => assertNativeIssueQuestionGovernance({
        kind,
        title: "Which source repository should be authorized?",
        payload: { question: "Pick the implementation path", options: ["Temporary worktree", "Production repository"] },
      }, AGENT)).toThrow("Agent technical or credential escalation");
    }
  });
  it("preserves governed native tool-action and protected proposal confirmation", () => {
    for (const payload of [{ toolAction: { id: "governed-action" } }, { secretProposal: { id: "governed-proposal" } }]) {
      expect(() => assertNativeIssueQuestionGovernance({
        kind: "request_confirmation",
        title: "Authorize controlled action",
        payload,
      }, AGENT)).not.toThrow();
    }
  });
  it("allows genuine product/editorial questions", () => {
    expect(() => assertNativeIssueQuestionGovernance(
      form("Wybierz styl", "Który styl ilustracji wybrać?", [
        "Płaski 2D", "Ręcznie rysowany",
      ]), AGENT,
    )).not.toThrow();
  });
  it("preserves native, governed grant and human approval flows", () => {
    expect(() => assertNativeIssueQuestionGovernance(
      { kind: "connection_intent", title: "Grant Ubuntu SSH access" }, AGENT,
    )).not.toThrow();
    expect(() => assertNativeIssueQuestionGovernance(
      { kind: "request_confirmation", title: "Authorize a native tool action" }, AGENT,
    )).not.toThrow();
  });
  it("does not restrict a board-authored question", () => {
    expect(() => assertNativeIssueQuestionGovernance(
      form("Which repo path?", "Which worktree?", ["A", "B"]), null,
    )).not.toThrow();
  });
});
