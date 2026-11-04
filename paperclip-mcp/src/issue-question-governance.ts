/**
 * Guardrail for issue-thread questions routed through paperclip-mcp.
 *
 * Native ask_user_questions currently uses a broadly answerable ('anyone')
 * interaction, so it MUST NOT serve as an authorization surface or a way to
 * punt implementation choices to a human. It cannot grant credentials.
 *
 * Deliberately scope this to technical/admin content: product/editorial
 * preference questions remain available. The first-class governed native
 * connection-intent / approval path is not changed here.
 */
export const TECHNICAL_QUESTION_DENIED =
  "TECHNICAL_QUESTION_REQUIRES_OWNER: Do not create an anyone-answerable " +
  "question/confirmation for credentials, permissions or engineering routing. " +
  "Use the native human_only connection-intent for an actual access grant, " +
  "or ask the assigned CTO/CHO to resolve the technical dependency. " +
  "Never request an admin token in issue questions.";

const PRIVILEGED_SUBJECT =
  /(?:\b(?:ssh|sudo|bearer|secrets?|tokens?|credentials?|grants?|permissions?|privileged|administrator|admin|api[-_ ]?key|service[-_ ]?identity|human[-_ ]?grant)\b|\bauthori[sz](?:e|ation|ed|ing)\b|\bauthentication\b|\baccess[-_ ]?(?:request|path|grant|token|credential)\b)/i;
const TECHNICAL_ROUTING =
  /(?:\b(?:worktree|workspace|repository|repo|github|gitops|docker|deployment|deploy|rollout|CI\/?CD|Hindsight|Hermes|Coolify|Plasmic|Paperclip|gateway|receiver|runtime|MCP|WAB|blockers?|dependency|release[-_ ]?gate|source[-_ ]?scope|environment[-_ ]?variables|provision|run[-_ ]?scoped)\b|\bPR\s*#\s*\d+\b)/i;

export function assertIssueQuestionGoverned(
  kind: string,
  input: unknown,
): void {
  if (!["ask_user_questions", "request_confirmation", "request_checkbox_confirmation"].includes(kind)) {
    return;
  }
  // Inputs are Zod-validated by the tool before this function is called.
  // Include option labels/descriptions: harmful offers are often only there.
  const content = JSON.stringify(input ?? "");
  if (PRIVILEGED_SUBJECT.test(content) || TECHNICAL_ROUTING.test(content)) {
    throw new Error(TECHNICAL_QUESTION_DENIED);
  }
}
