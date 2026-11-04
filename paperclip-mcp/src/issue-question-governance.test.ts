import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { PaperclipApiClient } from "./client.js";
import { createToolDefinitions } from "./tools.js";
import { assertIssueQuestionGoverned, TECHNICAL_QUESTION_DENIED } from "./issue-question-governance.js";

const client = () => new PaperclipApiClient({
  apiUrl: "http://localhost:3100/api",
  apiKey: "test-key",
  companyId: "11111111-1111-1111-1111-111111111111",
  agentId: "22222222-2222-2222-2222-222222222222",
  runId: "33333333-3333-4333-8333-333333333333",
  agentApiKey: "agent-key",
  boardApiKey: "board-key",
});
const form = (prompt: string, options: string[]) => ({
  version: 1 as const,
  questions: [{
    id: "choose",
    prompt,
    selectionMode: "single" as const,
    options: options.map((label, i) => ({ id: `opt_${i}`, label })),
  }],
});
function getTool(name: string) {
  const tool = createToolDefinitions(client()).find(t => t.name === name);
  if (!tool) throw Error(`Missing tool ${name}`);
  return tool;
}
function responseBody() {
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
describe("issue questions are not a credential or technical escalation channel", () => {
  beforeEach(() => {
    vi.stubEnv("PAPERCLIP_MCP_ENABLE_ALL", "1");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });
  it("rejects the KOMAA-1553 SSH/Hindsight admin bearer options before HTTP write", async () => {
    const fetchMock = vi.fn().mockResolvedValue(responseBody());
    vi.stubGlobal("fetch", fetchMock);
    const result = await getTool("paperclipAskUserQuestions").execute({
      issueId: "KOMAA-1553",
      title: "Which access path do you authorize?",
      payload: form("Which path?", ["Re-issue ssh_execute grant", "Provide Hindsight admin bearer", "Keep blocked"]),
    });
    expect(result.content[0]?.text).toContain("TECHNICAL_QUESTION_REQUIRES_OWNER");
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("rejects architecture/source-worktree choices without touching a live issue", async () => {
    expect(() => assertIssueQuestionGoverned("ask_user_questions", {
      title: "Choose an implementation path",
      payload: form("Which source workspace should we use?", ["Use PR #31", "Mount another worktree"]),
    })).toThrow(TECHNICAL_QUESTION_DENIED);
  });
  it("rejects euphemistic access and architecture questions but allows editorial product names", () => {
    for (const prompt of [
      "Which way should I sign in to the machine?",
      "Where should we mount the worktree for this implementation?",
    ]) {
      expect(() => assertIssueQuestionGoverned("ask_user_questions", {
        payload: form(prompt, ["Option A", "Option B"]),
      })).toThrow(TECHNICAL_QUESTION_DENIED);
    }
    expect(() => assertIssueQuestionGoverned("ask_user_questions", {
      payload: form("Which Paperclip description reads better?", ["Plasmic in the title", "Shorter wording"]),
    })).not.toThrow();
  });
  it("does not let an editorial title mask an operational prompt or option", () => {
    expect(() => assertIssueQuestionGoverned("ask_user_questions", {
      title: "Which description reads better?",
      payload: form("Which source workspace should we use?", ["Use PR #31"]),
    })).toThrow(TECHNICAL_QUESTION_DENIED);
    expect(() => assertIssueQuestionGoverned("ask_user_questions", {
      payload: form("Which Paperclip description reads better?", ["Which server should we deploy?", "Shorter wording"]),
    })).toThrow(TECHNICAL_QUESTION_DENIED);
  });
  it("rejects both confirmation tool paths before HTTP write", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    for (const [toolName, payload] of [
      ["paperclipRequestConfirmation", { version: 1, prompt: "Which way should I sign in to the machine?" }],
      ["paperclipRequestCheckboxConfirmation", {
        version: 1,
        prompt: "Choose the workspace to mount the worktree",
        options: [{ id: "one", label: "Use this workspace" }],
      }],
    ] as const) {
      const result = await getTool(toolName).execute({ issueId: "KOMAA-1553", title: "Choose a route", payload });
      expect(result.content[0]?.text, toolName).toContain("TECHNICAL_QUESTION_REQUIRES_OWNER");
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("rejects the generic paperclipApiRequest bypass before HTTP write", async () => {
    const fetchMock = vi.fn().mockResolvedValue(responseBody());
    vi.stubGlobal("fetch", fetchMock);
    const result = await getTool("paperclipApiRequest").execute({
      method: "POST",
      path: "/issues/KOMAA-1553/interactions",
      jsonBody: JSON.stringify({
        kind: "ask_user_questions",
        title: "Grant an API token?",
        payload: form("Select bearer route", ["Provide admin token"]),
      }),
    });
    expect(result.content[0]?.text).toContain("TECHNICAL_QUESTION_REQUIRES_OWNER");
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("rejects generic API confirmation-kind bypasses before HTTP write", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    for (const kind of ["request_confirmation", "request_checkbox_confirmation"]) {
      const result = await getTool("paperclipApiRequest").execute({
        method: "POST",
        path: "/issues/KOMAA-1553/interactions",
        jsonBody: JSON.stringify({ kind, payload: { prompt: "Which repository should host the runtime?" } }),
      });
      expect(result.content[0]?.text).toContain("TECHNICAL_QUESTION_REQUIRES_OWNER");
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("allows a normal editorial preference question and posts exactly once", async () => {
    const fetchMock = vi.fn().mockResolvedValue(responseBody());
    vi.stubGlobal("fetch", fetchMock);
    const result = await getTool("paperclipAskUserQuestions").execute({
      issueId: "KOMAA-1553",
      title: "Wariant tekstu",
      payload: form("Który opis bohatera jest lepszy?", ["Przyjazny", "Energiczny"]),
    });
    expect(result.content[0]?.text).not.toContain("TECHNICAL_QUESTION_REQUIRES_OWNER");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("does not interfere with native connection-intent or formal review controls", () => {
    expect(() => assertIssueQuestionGoverned("connection_intent", {
      title: "Grant Ubuntu SSH access?",
    })).not.toThrow();
    expect(() => assertIssueQuestionGoverned("review", {
      title: "Review a production change",
    })).not.toThrow();
  });
});
