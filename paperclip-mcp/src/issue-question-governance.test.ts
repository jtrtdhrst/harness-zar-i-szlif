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
  it("rejects a confirmation/checkbox permission-grant fallback", () => {
    for (const kind of ["request_confirmation", "request_checkbox_confirmation"]) {
      expect(() => assertIssueQuestionGoverned(kind, {
        title: "Approve SSH sudo permissions",
      })).toThrow(TECHNICAL_QUESTION_DENIED);
    }
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
