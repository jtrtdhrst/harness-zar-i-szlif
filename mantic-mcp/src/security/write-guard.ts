/**
 * Fail-closed write guard for the Mautic MCP transport boundary.
 *
 * Why this exists: ZARI-209 executed Mautic writes while the target host/tenant
 * was unknown. The tag-persistence fixes alone do not stop a model from issuing
 * a write, and a read-only identity tool is not enforcement — the decision has to
 * happen here, in `dispatchTool`, before any provider request is built.
 *
 * Model:
 *  - every tool is classified explicitly (`TOOL_EFFECTS`); an unclassified name
 *    is denied, so a newly added tool cannot silently become writable;
 *  - `read` tools pass unchanged (the read-only audit path must stay open);
 *  - `test-write` tools are the only grantable mutations, and only through an
 *    operator-pinned TEST-only grant: matching host/tenant/principal, matching
 *    tool allowlist, matching tag/recipient scope, and a future expiry;
 *  - every other mutation (`denied`) is refused unconditionally — send,
 *    activation, enrollment, campaign/segment/email/form/content/project writes
 *    stay impossible in this remediation even if a grant lists them.
 *
 * The operator values come from the deployment environment, which the model
 * cannot write. Nothing here is derived from tool arguments, issue comments or
 * model claims, and no grant content is ever echoed in a response or log.
 */
import { ErrorCode, McpError } from '../errors.js';
import { flattenContactPayload, normalizeTagList } from '../lib/contact-payload.js';
import { unexpectedArguments } from '../tools/fixture-graph.js';

export type ToolEffect = 'read' | 'test-write' | 'denied';

export const WRITE_GUARD_ERROR = 'WRITE_GUARD_DENIED';

export type DenialReason =
  | 'UNKNOWN_TOOL'
  | 'TOOL_DENIED'
  | 'NO_GRANT'
  | 'GRANT_INVALID'
  | 'GRANT_EXPIRED'
  | 'TENANT_MISMATCH'
  | 'HOST_MISMATCH'
  | 'PRINCIPAL_MISMATCH'
  | 'IDENTITY_UNAVAILABLE'
  | 'TOOL_NOT_GRANTED'
  | 'SCOPE_VIOLATION'
  | 'SHARED_TRANSPORT_DENIED';

/** Environment contract. Values are operator-pinned; none of them is a secret
 *  written by an agent, and the grant carries no provider credential. */
export const GUARD_ENV = {
  targetHost: 'MAUTIC_TARGET_HOST',
  targetTenant: 'MAUTIC_TARGET_TENANT',
  principal: 'MAUTIC_PRINCIPAL',
  grant: 'MAUTIC_WRITE_GRANT',
  identityTtlMs: 'MAUTIC_WRITE_GUARD_IDENTITY_TTL_MS',
  testIdentityClass: 'MAUTIC_TEST_IDENTITY_CLASS',
} as const;

/**
 * Graph creation is allowed only for a deployment whose credential is an
 * isolated TEST principal (owner directive 2026-11-16: fixtures run against the
 * real production Mautic, with a separate isolated test principal rather than a
 * separate installation). The shared stdio/HTTP provider has no trusted
 * per-agent identity, so it must not set this — its writes stay denied.
 */
export const ISOLATED_TEST_PRINCIPAL = 'isolated-test-principal';

/** Tools that additionally require an isolated TEST principal. */
export const ISOLATED_IDENTITY_TOOLS: ReadonlySet<string> = new Set(['provision_inactive_test_campaign']);

const DEFAULT_IDENTITY_TTL_MS = 60_000;

/**
 * Explicit classification of every advertised tool (69). Anything not listed is
 * denied at runtime by design.
 */
export const TOOL_EFFECTS: Readonly<Record<string, ToolEffect>> = Object.freeze({
  // --- reads: unchanged, no grant needed -----------------------------------
  get_contact: 'read',
  search_contacts: 'read',
  list_campaigns: 'read',
  get_campaign: 'read',
  get_campaign_contacts: 'read',
  export_campaign: 'read',
  get_campaign_event_details: 'read',
  get_campaign_graph_stats: 'read',
  get_campaign_map_stats: 'read',
  list_emails: 'read',
  get_email: 'read',
  get_email_stats: 'read',
  get_email_graph_stats: 'read',
  list_forms: 'read',
  get_form: 'read',
  get_form_submissions: 'read',
  list_segments: 'read',
  get_segment_contacts: 'read',
  list_assets: 'read',
  get_asset: 'read',
  list_pages: 'read',
  list_sms: 'read',
  list_companies: 'read',
  get_contact_notes: 'read',
  list_tags: 'read',
  list_categories: 'read',
  list_stages: 'read',
  list_contact_fields: 'read',
  get_contact_activity: 'read',
  list_webhooks: 'read',
  list_reports: 'read',
  list_projects: 'read',
  get_project: 'read',
  get_instance_identity: 'read',

  // --- TEST-only fixture writes: the only grantable mutations ---------------
  create_contact: 'test-write',
  update_contact: 'test-write',
  delete_contact: 'test-write',
  add_contact_tags: 'test-write',
  create_tag: 'test-write',
  // Inactive email+segment+campaign graph; additionally requires an isolated
  // TEST principal (see ISOLATED_IDENTITY_TOOLS).
  provision_inactive_test_campaign: 'test-write',

  // --- everything else mutating: denied unconditionally --------------------
  send_email: 'denied',
  send_email_to_segment: 'denied',
  record_email_reply: 'denied',
  create_email_template: 'denied',
  execute_campaign: 'denied',
  add_contact_to_campaign: 'denied',
  create_campaign: 'denied',
  create_campaign_with_automation: 'denied',
  clone_campaign: 'denied',
  import_campaign: 'denied',
  add_contact_to_segment: 'denied',
  create_segment: 'denied',
  create_asset: 'denied',
  create_page: 'denied',
  create_sms: 'denied',
  create_company: 'denied',
  add_contact_to_company: 'denied',
  create_note: 'denied',
  create_category: 'denied',
  add_contact_points: 'denied',
  subtract_contact_points: 'denied',
  change_contact_stage: 'denied',
  create_contact_field: 'denied',
  create_webhook: 'denied',
  upload_file: 'denied',
  create_report: 'denied',
  create_project: 'denied',
  update_project: 'denied',
  patch_project: 'denied',
  delete_project: 'denied',
});

/** Coarse class of every unconditionally denied tool, for the structured error. */
export const DENIED_TOOL_CLASS: Readonly<Record<string, string>> = Object.freeze({
  send_email: 'send',
  send_email_to_segment: 'send',
  record_email_reply: 'send',
  create_email_template: 'content',
  execute_campaign: 'activation',
  add_contact_to_campaign: 'enrollment',
  create_campaign: 'activation',
  create_campaign_with_automation: 'activation',
  clone_campaign: 'activation',
  import_campaign: 'activation',
  add_contact_to_segment: 'enrollment',
  create_segment: 'segment-mutation',
  create_asset: 'content',
  create_page: 'content',
  create_sms: 'content',
  create_company: 'mutation',
  add_contact_to_company: 'mutation',
  create_note: 'mutation',
  create_category: 'mutation',
  add_contact_points: 'mutation',
  subtract_contact_points: 'mutation',
  change_contact_stage: 'mutation',
  create_contact_field: 'mutation',
  create_webhook: 'integration',
  upload_file: 'integration',
  create_report: 'integration',
  create_project: 'api-v2',
  update_project: 'api-v2',
  patch_project: 'api-v2',
  delete_project: 'api-v2',
});

export interface WriteGrant {
  tenant: string;
  tools: string[];
  allowedTagPrefixes: string[];
  allowedContactEmails: string[];
  allowedFixturePrefixes: string[];
  /** Operator-pinned ZARI-208 creative artifact digests; empty means no artifact may be used. */
  pinnedArtifactSha256: string[];
  /** Must equal the pinned MAUTIC_PRINCIPAL: the grant is bound to the isolated test identity. */
  testPrincipal: string;
  scope: string;
  expiresAt: string;
}

const HINTS: Record<DenialReason, string> = {
  UNKNOWN_TOOL:
    'This tool has no write-guard classification, so it is treated as a mutation. Classify it explicitly or call a read tool.',
  TOOL_DENIED:
    'This mutation is outside the TEST-only remediation scope and cannot be granted in this build.',
  NO_GRANT:
    'No operator TEST-only write grant is configured for this deployment; Mautic mutations are denied by default.',
  GRANT_INVALID: 'The configured write grant is malformed and was rejected.',
  GRANT_EXPIRED: 'The configured TEST-only write grant has expired.',
  TENANT_MISMATCH: 'The grant tenant does not match the operator-pinned target tenant.',
  HOST_MISMATCH: 'The configured Mautic base host does not match the operator-pinned target host.',
  PRINCIPAL_MISMATCH:
    'The provider credential principal does not match the operator-pinned principal (checked at the provider, not from tool arguments).',
  IDENTITY_UNAVAILABLE:
    'The target identity could not be verified at the provider (base host or /users/self unavailable), so no mutation is allowed.',
  TOOL_NOT_GRANTED: 'The grant does not include this tool.',
  SCOPE_VIOLATION: 'The requested resource is outside the grant scope (TEST-only tags/recipients/fixture names).',
  SHARED_TRANSPORT_DENIED:
    'Fixture-graph creation requires a deployment carrying an isolated TEST principal (MAUTIC_TEST_IDENTITY_CLASS=' +
    'isolated-test-principal) whose grant names that principal. The shared stdio/HTTP provider has no trusted per-agent identity, ' +
    'so this write stays denied there and is an operator-side infrastructure action.',
};

function deny(
  tool: string,
  reason: DenialReason,
  targetHost: string | null,
  extra: Record<string, unknown> = {},
): never {
  const data = {
    error: WRITE_GUARD_ERROR,
    reason,
    tool,
    targetHost,
    ...extra,
  };
  throw new McpError(ErrorCode.InvalidRequest, `Write guard denied "${tool}": ${reason}. ${HINTS[reason]}`, data);
}

/** Minimal, anchored glob: `*` matches any run of characters. */
export function matchesGlob(pattern: string, value: string): boolean {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*');
  return new RegExp(`^${escaped}$`, 'i').test(value);
}

function parseGrant(raw: string | undefined): { grant: WriteGrant | null; error: DenialReason | null } {
  if (!raw || raw.trim() === '') return { grant: null, error: 'NO_GRANT' };
  let parsed: any;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { grant: null, error: 'GRANT_INVALID' };
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { grant: null, error: 'GRANT_INVALID' };
  }
  const stringArray = (value: un

... [13974 characters truncated]