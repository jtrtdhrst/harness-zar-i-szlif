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
const EDITORIAL_PURPOSE =
  /\b(?:which|what|pick|prefer|choose)\b.{0,50}\b(?:wording|copy|description|tone|name|title|illustration|character|mascot|design|style|variant|version|text|phrase)\b/i;
const OPERATIONAL_PURPOSE =
  /\b(?:which|what|where|how|choose|pick|select|decide|authorize|approve|should|can|could)\b.{0,100}\b(?:sign\s*in|log\s*in|connect|access|reach|use|run|deploy|release|build|host|mount|provision|route|source|workspace|worktree|repository|repo|branch|gateway|receiver|runtime|environment|credential|token|key|permission|grant|identity|machine|server|service|blocker|dependency|implementation|architecture|path|worktree|PR\s*#?\d*)\b/i;

// Editorial wording cannot exempt an explicit infrastructure action.
const EXPLICIT_DEPLOY_ACTION =
  /\b(?:deploy|release|merge|push|build|mount|provision|restart|migrate|install|route)\b.{0,80}\b(?:production|server|cluster|gateway|runtime|workspace|worktree|branch|repository|repo|environment|service|endpoint|host)\b/i;

export function assertIssueQuestionGoverned(
  kind: string,
  input: unknown,
): void {
  if (!["ask_user_questions", "request_confirmation", "request_checkbox_confirmation"].includes(kind)) {
    return;
  }
  // Inputs are Zod-validated. Inspect actual string VALUES, not JSON property
  // keys: e.g. a harmless "title" key must not imply editorial intent.
  // Check each option independently; an editorial prompt may not mask an
  // operational/credential choice hidden in an option label or description.
  const strings: string[] = [];
  const collect = (value: unknown): void => {
    if (typeof value === "string") strings.push(value);
    else if (Array.isArray(value)) value.forEach(collect);
    else if (value && typeof value === "object") Object.values(value).forEach(collect);
  };
  collect(input);
  if (PRIVILEGED_SUBJECT.test(strings.join("\n")) ||
      strings.some(text => OPERATIONAL_PURPOSE.test(text) &&
        (!EDITORIAL_PURPOSE.test(text) || EXPLICIT_DEPLOY_ACTION.test(text)))) {
    throw new Error(TECHNICAL_QUESTION_DENIED);
  }
}
