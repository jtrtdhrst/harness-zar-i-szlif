import { unprocessable } from "../errors.js";

/**
 * Fail closed for agent-created issue-thread forms which are being used to
 * outsource engineering work or to ask for secrets. This is server-side and
 * therefore covers direct REST calls as well as all MCP clients.
 *
 * Native connection_intent, genuine toolAction/secretProposal confirmations,
 * approvals, and end-user product/editorial preference questions are separate
 * workflows and are deliberately not modified here.
 */
export function assertNativeIssueQuestionGovernance(
  input: {
    kind: string;
    title?: string | null;
    summary?: string | null;
    payload?: unknown;
  },
  creatorAgentId: string | null,
): void {
  if (!creatorAgentId || input.kind !== "ask_user_questions") return;
  const text = JSON.stringify({
    title: input.title ?? "",
    summary: input.summary ?? "",
    payload: input.payload ?? null,
  });

  const privileged =
    /\b(?:ssh|sudo|bearer|secret(?:s)?|credential(?:s)?|privileged|administrator|admin|(?:api|service)[-_ ]?key|access[-_ ]?(?:grant|request|token|path)|grant(?:s)?|permissions?|token(?:s)?)\b/i;
  const operationalPath =
    /\b(?:worktree|source[-_ ]?(?:branch|path|scope|repository)|repository|gitops|docker|gateway[-_ ]?receiver|coolify|paperclip[-_ ]?core|runtime[-_ ]?source|deployment[-_ ]?gate|mcp[-_ ]?authorization)\b|\bPR\s*#\s*\d+\b/i;
  const decisionPrompt =
    /\b(?:authorize|authorization|approve|permission|choose|which|pick|select|provide|provision|grant|route|path|unblock|reassign|mount)\b/i;

  if (privileged.test(text) || (operationalPath.test(text) && decisionPrompt.test(text))) {
    throw unprocessable(
      "Agent technical or credential escalation cannot use ask_user_questions. " +
      "Use native human_only connection_intent for a real grant; otherwise route " +
      "engineering work to its assigned CTO/CHO without an everyone-answerable form.",
      { code: "ISSUE_QUESTION_TECHNICAL_ESCALATION_DENIED" },
    );
  }
}
