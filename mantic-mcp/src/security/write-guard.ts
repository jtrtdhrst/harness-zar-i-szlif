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
  deploymentClass: 'MAUTIC_DEPLOYMENT_CLASS',
} as const;

/**
 * The only deployment class allowed to create fixture graphs. The shared
 * stdio/HTTP provider has no trusted per-agent identity, so graph creation stays
 * denied there and requires an explicitly dedicated, single-principal TEST
 * deployment (operator-set environment; a model cannot set it).
 */
export const DEDICATED_TEST_CLASS = 'dedicated-test';

/** Tools that additionally require a dedicated TEST deployment. */
export const DEDICATED_DEPLOYMENT_TOOLS: ReadonlySet<string> = new Set(['provision_inactive_test_campaign']);

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
  // Inactive email+segment+campaign graph; additionally requires a dedicated
  // TEST deployment (see DEDICATED_DEPLOYMENT_TOOLS).
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
    'Fixture-graph creation requires a dedicated TEST deployment (MAUTIC_DEPLOYMENT_CLASS=dedicated-test). The shared stdio/HTTP ' +
    'provider has no trusted per-agent identity, so this write stays denied there and is an operator-side infrastructure gate.',
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
  const stringArray = (value: unknown): string[] =>
    Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

  const grant: WriteGrant = {
    tenant: typeof parsed.tenant === 'string' ? parsed.tenant : '',
    tools: stringArray(parsed.tools),
    allowedTagPrefixes: stringArray(parsed.allowedTagPrefixes),
    allowedContactEmails: stringArray(parsed.allowedContactEmails),
    allowedFixturePrefixes: stringArray(parsed.allowedFixturePrefixes),
    scope: typeof parsed.scope === 'string' ? parsed.scope : '',
    expiresAt: typeof parsed.expiresAt === 'string' ? parsed.expiresAt : '',
  };

  if (grant.scope !== 'test-only') return { grant: null, error: 'GRANT_INVALID' };
  if (grant.tenant === '' || grant.tools.length === 0) return { grant: null, error: 'GRANT_INVALID' };
  if (Number.isNaN(Date.parse(grant.expiresAt))) return { grant: null, error: 'GRANT_INVALID' };
  return { grant, error: null };
}

export interface WriteGuardOptions {
  now?: () => number;
}

/**
 * Transport-boundary guard. One instance per server process; `authorize` is
 * called for every tool call before the handler is dispatched.
 */
export class WriteGuard {
  private readonly env: Record<string, string | undefined>;
  private readonly now: () => number;
  private identity: { key: string; expiresAt: number } | null = null;

  constructor(env: Record<string, string | undefined> = {}, options: WriteGuardOptions = {}) {
    this.env = env ?? {};
    this.now = options.now ?? (() => Date.now());
  }

  get targetHost(): string | null {
    return this.env[GUARD_ENV.targetHost]?.trim() || null;
  }

  get targetTenant(): string | null {
    return this.env[GUARD_ENV.targetTenant]?.trim() || null;
  }

  get principal(): string | null {
    return this.env[GUARD_ENV.principal]?.trim() || null;
  }

  private get identityTtlMs(): number {
    const raw = Number(this.env[GUARD_ENV.identityTtlMs]);
    return Number.isFinite(raw) && raw >= 0 ? raw : DEFAULT_IDENTITY_TTL_MS;
  }

  /** Non-secret summary for startup logging and issue evidence. */
  describe(): string {
    const grantState = parseGrant(this.env[GUARD_ENV.grant]).grant ? 'present' : 'absent';
    const counts = { read: 0, 'test-write': 0, denied: 0 } as Record<string, number>;
    for (const effect of Object.values(TOOL_EFFECTS)) counts[effect] += 1;
    return (
      `mode=enforce grant=${grantState} pinnedHost=${this.targetHost ?? 'unset'} ` +
      `pinnedTenantSet=${this.targetTenant ? 'yes' : 'no'} principalSet=${this.principal ? 'yes' : 'no'} ` +
      `deploymentClass=${this.env[GUARD_ENV.deploymentClass]?.trim() || 'unset'} ` +
      `tools: read=${counts.read} test-write=${counts['test-write']} denied=${counts.denied}`
    );
  }

  /** Throws a sanitized structured McpError when the call must not reach Mautic. */
  async authorize(toolName: string, client: any, args: any): Promise<void> {
    const effect = TOOL_EFFECTS[toolName];
    const host = this.targetHost;

    if (effect === undefined) deny(toolName, 'UNKNOWN_TOOL', host);
    if (effect === 'read') return;
    if (effect === 'denied') {
      deny(toolName, 'TOOL_DENIED', host, { toolClass: DENIED_TOOL_CLASS[toolName] ?? 'mutation' });
    }

    const { grant, error } = parseGrant(this.env[GUARD_ENV.grant]);
    if (!grant) deny(toolName, error ?? 'NO_GRANT', host);

    const tenant = this.targetTenant;
    if (!tenant || grant.tenant !== tenant) deny(toolName, 'TENANT_MISMATCH', host);

    if (Date.parse(grant.expiresAt) <= this.now()) deny(toolName, 'GRANT_EXPIRED', host);

    if (!grant.tools.includes(toolName)) deny(toolName, 'TOOL_NOT_GRANTED', host);

    // Fixture-graph creation is refused unless the deployment itself is declared
    // a dedicated TEST instance: the shared transport cannot prove a per-agent
    // actor, so it must not be able to create campaigns/segments/templates.
    if (DEDICATED_DEPLOYMENT_TOOLS.has(toolName)) {
      const deploymentClass = this.env[GUARD_ENV.deploymentClass]?.trim();
      if (deploymentClass !== DEDICATED_TEST_CLASS) {
        deny(toolName, 'SHARED_TRANSPORT_DENIED', host, {
          requiredDeploymentClass: DEDICATED_TEST_CLASS,
          observedDeploymentClass: deploymentClass ?? null,
        });
      }
    }

    const identity = await this.verifyIdentity(client);
    if (!identity.ok) deny(toolName, identity.reason, host);

    const violation = await this.checkScope(toolName, client, args, grant);
    if (violation) deny(toolName, 'SCOPE_VIOLATION', host, { scopeDetail: violation });
  }

  /**
   * Authoritative identity check: the configured base host must equal the pinned
   * host, and the provider's own `/users/self` answer must name the pinned
   * principal. Successful checks are cached briefly so a write batch does not
   * re-probe on every call.
   */
  private async verifyIdentity(
    client: any,
  ): Promise<{ ok: true; host: string } | { ok: false; reason: DenialReason }> {
    const pinnedHost = this.targetHost;
    const pinnedPrincipal = this.principal;
    if (!pinnedHost || !pinnedPrincipal) return { ok: false, reason: 'IDENTITY_UNAVAILABLE' };

    const baseUrl = typeof client?.getBaseUrl === 'function' ? client.getBaseUrl() : null;
    if (typeof baseUrl !== 'string' || baseUrl === '') return { ok: false, reason: 'IDENTITY_UNAVAILABLE' };

    let host: string;
    try {
      host = new URL(baseUrl).host.toLowerCase();
    } catch {
      return { ok: false, reason: 'HOST_MISMATCH' };
    }
    if (host !== pinnedHost.toLowerCase()) return { ok: false, reason: 'HOST_MISMATCH' };

    const cacheKey = `${host}|${pinnedPrincipal.toLowerCase()}`;
    if (this.identity && this.identity.key === cacheKey && this.identity.expiresAt > this.now()) {
      return { ok: true, host };
    }

    let identity: { username?: unknown; email?: unknown };
    try {
      const response = await client.v1.get('/users/self');
      const user = response?.data?.user ?? response?.data ?? {};
      identity = { username: user.username, email: user.email };
    } catch {
      return { ok: false, reason: 'IDENTITY_UNAVAILABLE' };
    }

    const actual = [identity.username, identity.email]
      .filter((value): value is string => typeof value === 'string' && value !== '')
      .map((value) => value.toLowerCase());
    if (!actual.includes(pinnedPrincipal.toLowerCase())) return { ok: false, reason: 'PRINCIPAL_MISMATCH' };

    this.identity = { key: cacheKey, expiresAt: this.now() + this.identityTtlMs };
    return { ok: true, host };
  }

  /**
   * Least-privilege resource scope for the grantable fixture tools.
   *
   * Two rules keep this honest (review round 2):
   *  1. tags are read through the *same* normalisation the payload builder uses
   *     (`flattenContactPayload` / `normalizeTagList`), so no accepted input
   *     representation — `{tag}` objects included — can reach the provider
   *     without being scope-checked;
   *  2. every contact-scoped write resolves the **target** contact at the
   *     provider and applies the recipient rule to its real e-mail, exactly like
   *     `delete_contact`. A requested e-mail is never evidence of target
   *     identity, and an unreadable target or a target without a verifiable
   *     e-mail is a denial, not a pass.
   */
  private async checkScope(
    toolName: string,
    client: any,
    args: any,
    grant: WriteGrant,
  ): Promise<Record<string, unknown> | null> {
    const tagViolation = (tags: string[]): Record<string, unknown> | null => {
      const rejected = tags.filter(
        (tag) => !grant.allowedTagPrefixes.some((prefix) => prefix !== '' && tag.startsWith(prefix)),
      );
      return rejected.length > 0
        ? { field: 'tags', reason: 'tag-not-in-grant-scope', rejectedCount: rejected.length }
        : null;
    };

    const recipientViolation = (email: unknown, field: string): Record<string, unknown> | null => {
      if (typeof email !== 'string' || email.trim() === '') {
        return { field, reason: 'recipient-not-in-grant-scope', rejectedCount: 1 };
      }
      const allowed = grant.allowedContactEmails.some((pattern) => matchesGlob(pattern, email));
      return allowed ? null : { field, reason: 'recipient-not-in-grant-scope', rejectedCount: 1 };
    };

    /** Resolve the contact the write would act on and check its real address. */
    const targetViolation = async (id: unknown): Promise<Record<string, unknown> | null> => {
      if (id === undefined || id === null || id === '') {
        return { field: 'id', reason: 'recipient-not-in-grant-scope', rejectedCount: 1 };
      }
      let contact: any;
      try {
        const response = await client.v1.get(`/contacts/${id}`);
        contact = response?.data?.contact ?? {};
      } catch {
        return { field: 'targetContact', reason: 'target-not-verifiable', rejectedCount: 1 };
      }
      return recipientViolation(contact?.email, 'targetContactEmail');
    };

    const requireTags = (value: unknown): Record<string, unknown> | null => {
      const tags = normalizeTagList(value);
      if (tags.length === 0) return { field: 'tags', reason: 'tag-not-in-grant-scope', rejectedCount: 1 };
      return tagViolation(tags);
    };

    if (toolName === 'create_tag') {
      const tags = normalizeTagList([args?.tag]);
      if (tags.length === 0) return { field: 'tag', reason: 'tag-not-in-grant-scope', rejectedCount: 1 };
      return tagViolation(tags);
    }

    if (toolName === 'add_contact_tags') {
      const tagCheck = requireTags(args?.tags);
      if (tagCheck) return tagCheck;
      // The tag write lands on a specific contact: scope is the recipient, not
      // just the tag name.
      return targetViolation(args?.contactId);
    }

    if (toolName === 'create_contact' || toolName === 'update_contact') {
      // Exactly the body the handler will send — one normalisation path.
      const payload = flattenContactPayload(args, { omit: toolName === 'update_contact' ? ['id'] : [] });
      if (Object.prototype.hasOwnProperty.call(payload, 'tags')) {
        const tagCheck = tagViolation(normalizeTagList(payload.tags));
        if (tagCheck) return tagCheck;
      }
      if (toolName === 'update_contact') {
        const target = await targetViolation(args?.id);
        if (target) return target;
      }
      // The address being written must be in scope too, so a fixture contact
      // cannot be moved onto a real customer address.
      if (payload.email !== undefined) return recipientViolation(payload.email, 'email');
      if (toolName === 'create_contact') return recipientViolation(undefined, 'email');
      return null;
    }

    if (toolName === 'delete_contact') {
      return targetViolation(args?.id);
    }

    if (toolName === 'provision_inactive_test_campaign') {
      // Fail-closed argument surface: activation/send/recipient/update keys are
      // not "ignored", they are a denial.
      const unexpected = unexpectedArguments(args);
      if (unexpected.length > 0) {
        return { field: 'arguments', reason: 'unsupported-argument', rejectedNames: unexpected };
      }
      const prefixOk = (value: unknown) =>
        typeof value === 'string' &&
        grant.allowedFixturePrefixes.some((prefix) => prefix !== '' && value.startsWith(prefix));
      for (const field of ['emailName', 'segmentName', 'campaignName'] as const) {
        if (!prefixOk(args?.[field])) {
          return { field, reason: 'fixture-name-not-in-grant-scope', rejectedCount: 1 };
        }
      }
      const tagName = typeof args?.tagName === 'string' ? args.tagName.trim() : '';
      if (tagName === '' || !grant.allowedTagPrefixes.some((prefix) => prefix !== '' && tagName.startsWith(prefix))) {
        return { field: 'tagName', reason: 'tag-not-in-grant-scope', rejectedCount: 1 };
      }
      return null;
    }

    return null;
  }
}
