/**
 * `provision_inactive_test_campaign` — the only grantable way to create an
 * inbound test graph (email template + tag-filtered segment + INACTIVE campaign
 * with one non-executing `email.send` action) without opening the general
 * create tools.
 *
 * Guarantees (review round 4, independent CHO findings F1-F4):
 *  F1  the campaign carries exactly one `email.send` event bound to the email id
 *      created by this call, and the campaign/segment stay unpublished, so
 *      nothing can execute; the readback must show that event.
 *  F2  every success predicate is positively established by provider readback —
 *      publication state must be an explicit value (a missing field is
 *      NOT_VERIFIED, never "unpublished"), the tag filter must persist, and the
 *      campaign source list must be present and reference the new segment.
 *  F3  creation is idempotent by exact name and partially reversible: existing
 *      fixtures are reused instead of duplicated, and a failure after a create
 *      deletes only ids this invocation created (never pre-existing objects),
 *      reporting anything the provider refused to delete.
 *  F4  the email body is bound to the ZARI-208 artifact: the caller must supply
 *      `artifactSha256`, the body must hash to it, and the guard requires that
 *      hash to be operator-pinned in the grant — arbitrary or altered HTML is
 *      refused and no HTML is ever manufactured.
 *
 * The campaign entry source is the SEGMENT (`lists`), a supported Mautic source.
 * A tag-change decision (`lead.changetags`) is an in-campaign event and is never
 * created or described as a contact source here.
 */
import { createHash } from 'node:crypto';
import type { MauticApiClient } from '../api/client.js';
import { ErrorCode, McpError } from '../errors.js';
import type { ToolDefinition, ToolHandler } from '../types/index.js';

export const NOT_VERIFIED = 'NOT_VERIFIED';

/** Explicit publication state: true/false, or null when the provider does not say. */
export function publicationState(value: unknown): boolean | null {
  if (value === true || value === 1 || value === '1' || value === 'true') return true;
  if (value === false || value === 0 || value === '0' || value === 'false') return false;
  return null;
}

export function sha256Hex(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

function requireId(value: unknown, what: string): string | number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') return value.trim();
  throw new McpError(
    ErrorCode.InternalError,
    `provision_inactive_test_campaign: NOT_VERIFIED - ${what} was created but the provider returned no id. Do not report this as success.`,
    { error: NOT_VERIFIED, resource: what },
  );
}

function originOf(baseUrl: string | null): string | null {
  if (!baseUrl) return null;
  try {
    return new URL(baseUrl).origin;
  } catch {
    return null;
  }
}

/** Exact-name lookup so a retry reuses instead of duplicating. */
function pickByName(collection: unknown, name: string): any | null {
  if (!collection || typeof collection !== 'object') return null;
  const items = Array.isArray(collection) ? collection : Object.values(collection as Record<string, any>);
  for (const item of items) {
    if (item && typeof item === 'object' && item.name === name) return item;
  }
  return null;
}

export const toolDefinitions: ToolDefinition[] = [
  {
    name: 'provision_inactive_test_campaign',
    description:
      'Create an INACTIVE test graph in one call: an unpublished email template bound to the pinned ZARI-208 artifact hash, an ' +
      'unpublished segment filtered on one tag, and an unpublished campaign whose only contact source is that segment and whose only ' +
      'action is one non-executing email.send event pointing at that email. Refuses on a shared deployment, without a TEST-only ' +
      'grant, or when any publish/send/activate/recipient/update field is supplied. Idempotent by exact name and partially reversible. ' +
      'Every predicate is read back; a missing or ambiguous provider value fails the call with NOT_VERIFIED. A tag change is not a ' +
      'campaign entry source.',
    inputSchema: {
      type: 'object',
      properties: {
        emailName: { type: 'string', description: 'Email template name (must match a granted fixture prefix)' },
        emailSubject: { type: 'string', description: 'Email subject' },
        customHtml: { type: 'string', description: 'Email HTML body; must hash to artifactSha256' },
        artifactSha256: {
          type: 'string',
          description: 'SHA-256 of customHtml; must equal the operator-pinned ZARI-208 artifact hash',
        },
        segmentName: { type: 'string', description: 'Segment name (must match a granted fixture prefix)' },
        campaignName: { type: 'string', description: 'Campaign name (must match a granted fixture prefix)' },
        tagName: { type: 'string', description: 'Tag the segment filters on (must match a granted tag prefix)' },
      },
      required: ['emailName', 'emailSubject', 'customHtml', 'artifactSha256', 'segmentName', 'campaignName', 'tagName'],
    },
  },
];

/**
 * Argument names this tool will ever accept. Anything else — `isPublished`,
 * `publishUp`, `events`, `lists`, `contactIds`, `recipients`, `id`, … — is
 * refused before a single provider request, so activation cannot be smuggled
 * in through an unexpected key.
 */
export const ALLOWED_ARGUMENTS: ReadonlySet<string> = new Set([
  'emailName',
  'emailSubject',
  'customHtml',
  'artifactSha256',
  'segmentName',
  'campaignName',
  'tagName',
]);

export function unexpectedArguments(args: Record<string, unknown> | undefined | null): string[] {
  return Object.keys(args ?? {}).filter((key) => !ALLOWED_ARGUMENTS.has(key));
}

/** The documented Mautic segment filter for a contact tag (text field, `like`). */
export function tagSegmentFilter(tagName: string): Record<string, unknown> {
  return {
    glue: 'and',
    field: 'tags',
    object: 'lead',
    type: 'text',
    operator: 'like',
    properties: { filter: tagName },
  };
}

/** The single non-executing campaign action this tool may create. */
export function emailSendEvent(emailId: string | number, campaignName: string): Record<string, unknown> {
  return {
    id: 'new1',
    name: `${campaignName} (inactive email action)`,
    type: 'email.send',
    eventType: 'action',
    order: 1,
    properties: { email: emailId },
    triggerMode: 'immediate',
  };
}

export const toolHandlers: Record<string, ToolHandler> = {
  async provision_inactive_test_campaign(client: MauticApiClient, args: any) {
    const unexpected = unexpectedArguments(args);
    if (unexpected.length > 0) {
      throw new McpError(
        ErrorCode.InvalidParams,
        `provision_inactive_test_campaign: unsupported argument(s) ${unexpected.join(', ')}. This tool only creates inactive fixtures; ` +
          'publish, send, activation, recipient, event and update fields are not accepted.',
      );
    }

    const emailName = String(args?.emailName ?? '').trim();
    const emailSubject = String(args?.emailSubject ?? '').trim();
    const segmentName = String(args?.segmentName ?? '').trim();
    const campaignName = String(args?.campaignName ?? '').trim();
    const tagName = String(args?.tagName ?? '').trim();
    const customHtml = typeof args?.customHtml === 'string' ? args.customHtml : '';
    const claimedArtifact = String(args?.artifactSha256 ?? '').trim().toLowerCase();

    for (const [field, value] of Object.entries({ emailName, emailSubject, segmentName, campaignName, tagName, customHtml })) {
      if (value === '') throw new McpError(ErrorCode.InvalidParams, `provision_inactive_test_campaign: ${field} is required`);
    }
    if (!/^[0-9a-f]{64}$/.test(claimedArtifact)) {
      throw new McpError(ErrorCode.InvalidParams, 'provision_inactive_test_campaign: artifactSha256 must be a 64-character hex digest');
    }
    const actualArtifact = sha256Hex(customHtml);
    if (actualArtifact !== claimedArtifact) {
      throw new McpError(
        ErrorCode.InvalidParams,
        'provision_inactive_test_campaign: customHtml does not hash to artifactSha256; the body is not the claimed artifact.',
        { error: 'ARTIFACT_MISMATCH', claimedArtifact, actualArtifact },
      );
    }

    const origin = originOf(typeof client?.getBaseUrl === 'function' ? client.getBaseUrl() : null);
    const createdNow: Array<{ kind: 'email' | 'segment' | 'campaign'; id: string | number }> = [];
    const reused: Record<string, string | number> = {};
    const filter = tagSegmentFilter(tagName);

    /** Delete only ids created by this invocation; never touch pre-existing objects. */
    const compensate = async (): Promise<{ deleted: string[]; failed: string[] }> => {
      const deleted: string[] = [];
      const failed: string[] = [];
      for (const item of [...createdNow].reverse()) {
        const path =
          item.kind === 'email'
            ? `/emails/${item.id}/delete`
            : item.kind === 'segment'
              ? `/segments/${item.id}/delete`
              : `/campaigns/${item.id}/delete`;
        try {
          await client.v1.delete(path);
          deleted.push(`${item.kind}:${item.id}`);
        } catch {
          failed.push(`${item.kind}:${item.id}`);
        }
      }
      return { deleted, failed };
    };

    const fail = async (detail: string, extra: Record<string, unknown> = {}): Promise<never> => {
      const compensation = createdNow.length > 0 ? await compensate() : { deleted: [], failed: [] };
      throw new McpError(
        ErrorCode.InternalError,
        `provision_inactive_test_campaign: NOT_VERIFIED - ${detail}. No success is claimed. Compensation: deleted ` +
          `${JSON.stringify(compensation.deleted)}` +
          (compensation.failed.length > 0 ? `, provider refused ${JSON.stringify(compensation.failed)}` : ''),
        { error: NOT_VERIFIED, detail, created: createdNow, reused, compensation, ...extra },
      );
    };

    const findExisting = async (
      listPath: string,
      collectionKey: string,
      name: string,
    ): Promise<{ state: 'found'; id: string | number } | { state: 'absent' } | { state: 'inconclusive'; reason: string }> => {
      let response;
      try {
        response = await client.v1.get(listPath, { params: { search: `name:${name}`, limit: 5 } });
      } catch (error) {
        // A transient or refused lookup must not be read as "does not exist":
        // creating blind here would defeat idempotency and duplicate fixtures.
        return { state: 'inconclusive', reason: (error as Error)?.message ?? String(error) };
      }
      const collection = response?.data?.[collectionKey];
      if (!collection || typeof collection !== 'object') {
        return { state: 'inconclusive', reason: 'provider returned no collection for the name search' };
      }
      const found = pickByName(collection, name);
      if (found && found.id !== undefined && found.id !== null) return { state: 'found', id: found.id };
      return { state: 'absent' };
    };

    // ---- 1. email template (reuse an exact-name template when present)
    let emailId: string | number;
    const existingEmail = await findExisting('/emails', 'emails', emailName);
    if (existingEmail.state === 'inconclusive') {
      return fail(`email name lookup was inconclusive (${existingEmail.reason}); refusing to create blind`, { lookup: 'email' });
    }
    if (existingEmail.state === 'found') {
      emailId = existingEmail.id;
      reused.email = emailId;
    } else {
      let response;
      try {
        response = await client.v1.post('/emails/new', {
          name: emailName,
          subject: emailSubject,
          customHtml,
          emailType: 'template',
          isPublished: false,
        });
      } catch (error) {
        return fail(`email template creation failed: ${(error as Error)?.message ?? error}`);
      }
      emailId = requireId(response?.data?.email?.id, 'email template');
      createdNow.push({ kind: 'email', id: emailId });
    }

    const emailReadback = await client.v1.get(`/emails/${emailId}`).catch(() => null);
    const emailPersisted = emailReadback?.data?.email ?? null;
    if (!emailPersisted) return fail(`email template ${emailId} could not be read back`, { emailId });
    const emailState = publicationState(emailPersisted.isPublished);
    if (emailState === null) return fail(`email template ${emailId} read back without a publication state`, { emailId });
    if (emailState === true) return fail(`email template ${emailId} persisted as PUBLISHED`, { emailId });
    // The persisted body must itself be the pinned artifact: hashing the request
    // we sent is not evidence about what the provider stored.
    if (typeof emailPersisted.customHtml !== 'string' || emailPersisted.customHtml === '') {
      return fail(`email template ${emailId} read back without its persisted body; the artifact cannot be verified`, { emailId });
    }
    const persistedArtifact = sha256Hex(emailPersisted.customHtml);
    if (persistedArtifact !== actualArtifact) {
      return fail(`email template ${emailId} persisted a body that does not hash to the pinned artifact`, {
        emailId,
        persistedArtifact,
      });
    }

    // ---- 2. segment filtered on exactly one granted tag
    let segmentId: string | number;
    const existingSegment = await findExisting('/segments', 'lists', segmentName);
    if (existingSegment.state === 'inconclusive') {
      return fail(`segment name lookup was inconclusive (${existingSegment.reason}); refusing to create blind`, { lookup: 'segment' });
    }
    if (existingSegment.state === 'found') {
      segmentId = existingSegment.id;
      reused.segment = segmentId;
    } else {
      let response;
      try {
        response = await client.v1.post('/segments/new', { name: segmentName, isPublished: false, filters: [filter] });
      } catch (error) {
        return fail(`segment creation failed: ${(error as Error)?.message ?? error}`);
      }
      segmentId = requireId(response?.data?.list?.id, 'segment');
      createdNow.push({ kind: 'segment', id: segmentId });
    }

    const segmentReadback = await client.v1.get(`/segments/${segmentId}`).catch(() => null);
    const segmentPersisted = segmentReadback?.data?.list ?? null;
    if (!segmentPersisted) return fail(`segment ${segmentId} could not be read back`, { segmentId });
    const segmentState = publicationState(segmentPersisted.isPublished);
    if (segmentState === null) return fail(`segment ${segmentId} read back without a publication state`, { segmentId });
    if (segmentState === true) return fail(`segment ${segmentId} persisted as PUBLISHED`, { segmentId });
    const persistedFilters = Array.isArray(segmentPersisted.filters) ? segmentPersisted.filters : [];
    const tagFilterPersisted = persistedFilters.some(
      (item: any) => item?.field === 'tags' && String(item?.properties?.filter ?? item?.filter ?? '') === tagName,
    );
    if (!tagFilterPersisted) {
      return fail(`segment ${segmentId} read back without the tag filter on "${tagName}"`, { segmentId, tagFilterPersisted });
    }

    // ---- 3. campaign: segment source + exactly one inactive email.send action
    const event = emailSendEvent(emailId, campaignName);
    let campaignId: string | number;
    const existingCampaign = await findExisting('/campaigns', 'campaigns', campaignName);
    if (existingCampaign.state === 'inconclusive') {
      return fail(`campaign name lookup was inconclusive (${existingCampaign.reason}); refusing to create blind`, { lookup: 'campaign' });
    }
    if (existingCampaign.state === 'found') {
      campaignId = existingCampaign.id;
      reused.campaign = campaignId;
    } else {
      let response;
      try {
        response = await client.v1.post('/campaigns/new', {
          name: campaignName,
          isPublished: false,
          lists: [{ id: segmentId }],
          events: [event],
        });
      } catch (error) {
        return fail(`campaign creation failed: ${(error as Error)?.message ?? error}`);
      }
      campaignId = requireId(response?.data?.campaign?.id, 'campaign');
      createdNow.push({ kind: 'campaign', id: campaignId });
    }

    const campaignReadback = await client.v1.get(`/campaigns/${campaignId}`).catch(() => null);
    const campaignPersisted = campaignReadback?.data?.campaign ?? null;
    if (!campaignPersisted) return fail(`campaign ${campaignId} could not be read back`, { campaignId });
    const campaignState = publicationState(campaignPersisted.isPublished);
    if (campaignState === null) return fail(`campaign ${campaignId} read back without a publication state`, { campaignId });
    if (campaignState === true) return fail(`campaign ${campaignId} persisted as PUBLISHED`, { campaignId });

    if (!Array.isArray(campaignPersisted.lists)) {
      return fail(`campaign ${campaignId} read back without its contact source list`, { campaignId });
    }
    const sourceMatches = campaignPersisted.lists.some((item: any) => String(item?.id ?? item) === String(segmentId));
    if (!sourceMatches) {
      return fail(`campaign ${campaignId} does not list segment ${segmentId} as its contact source`, { campaignId });
    }

    const persistedEvents = campaignPersisted.events;
    const eventList: any[] =
      persistedEvents && typeof persistedEvents === 'object' ? Object.values(persistedEvents as Record<string, any>) : [];
    if (eventList.length !== 1) {
      return fail(`campaign ${campaignId} read back with ${eventList.length} event(s); exactly one email.send action is expected`, {
        campaignId,
      });
    }
    const persistedEvent = eventList[0];
    if (persistedEvent?.type !== 'email.send') {
      return fail(`campaign ${campaignId} event is "${persistedEvent?.type}", not email.send`, { campaignId });
    }
    if (String(persistedEvent?.properties?.email ?? '') !== String(emailId)) {
      return fail(`campaign ${campaignId} email action does not reference email ${emailId}`, { campaignId });
    }

    const payload = {
      provisioned: true,
      artifact: { sha256: actualArtifact, persistedSha256: persistedArtifact, verified: true },
      created: {
        email: {
          id: emailId,
          name: emailName,
          reused: reused.email !== undefined,
          persistedIsPublished: emailState,
          sourceLink: origin ? `${origin}/s/emails/edit/${emailId}` : null,
        },
        segment: {
          id: segmentId,
          name: segmentName,
          reused: reused.segment !== undefined,
          persistedIsPublished: segmentState,
          filter,
          filterPersisted: tagFilterPersisted,
          sourceLink: origin ? `${origin}/s/segments/edit/${segmentId}` : null,
        },
        campaign: {
          id: campaignId,
          name: campaignName,
          reused: reused.campaign !== undefined,
          persistedIsPublished: campaignState,
          entrySource: 'segment (campaign lists)',
          sourceMatches,
          events: [{ type: persistedEvent.type, emailId }],
          sourceLink: origin ? `${origin}/s/campaigns/edit/${campaignId}` : null,
        },
      },
      activation: 'inactive - campaign and segment unpublished, nothing sent, no cron or trigger executed',
      tagDependentEntry:
        'the campaign enters contacts through the tag-filtered segment (supported campaign source); a tag change is not an entry source',
      notRun: [
        'tag-dependent entry with real contacts (needs a live provider test)',
        'duplicate suppression',
        'opt-out/do-not-contact suppression',
        'email rendering/delivery',
      ],
    };

    return {
      content: [
        {
          type: 'text',
          text: `Inactive test graph provisioned and read back:\n${JSON.stringify(payload, null, 2)}`,
        },
      ],
    };
  },
};
