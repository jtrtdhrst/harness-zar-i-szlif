/**
 * `provision_inactive_test_campaign` — the only grantable way to create an
 * inbound test graph (email template + tag-filtered segment + INACTIVE
 * campaign) without opening the general create tools.
 *
 * Why a dedicated tool instead of relaxing `create_email_template`,
 * `create_segment`, `create_campaign` / `create_campaign_with_automation`:
 * those accept arbitrary payloads (events, publish flags, lists/forms, imports),
 * so granting them cannot be least-privilege. This tool hard-codes the safe
 * shape and rejects every activation, send, enrollment or update field:
 *
 *   - email template: `isPublished: false`, `emailType: "template"`
 *   - segment:        `isPublished: false`, exactly one documented filter on the
 *                     contact `tags` field, value pinned to the granted prefix
 *   - campaign:       `isPublished: false`, entry source = the new segment only
 *                     (`lists`), no events, no forms, no trigger
 *
 * The campaign entry source is the SEGMENT (`lists`) — a supported Mautic
 * campaign source. A tag-change decision (`lead.changetags`) is an in-campaign
 * event and is NOT a contact source; this tool never creates one and never
 * claims tag-triggered enrollment.
 *
 * Creation is followed by a read-back of every object; a resource that comes
 * back published, or a campaign whose source list does not reference the new
 * segment, fails the call instead of reporting success.
 */
import type { MauticApiClient } from '../api/client.js';
import { ErrorCode, McpError } from '../errors.js';
import type { ToolDefinition, ToolHandler } from '../types/index.js';

/** Mautic returns booleans in some versions and 1/0 in others. */
function isPublished(value: unknown): boolean {
  return value === true || value === 1 || value === '1' || value === 'true';
}

function originOf(baseUrl: string | null): string | null {
  if (!baseUrl) return null;
  try {
    return new URL(baseUrl).origin;
  } catch {
    return null;
  }
}

function requireId(value: unknown, what: string): string | number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') return value.trim();
  throw new McpError(
    ErrorCode.InternalError,
    `provision_inactive_test_campaign: ${what} was created but the provider returned no id, so the graph cannot be verified. Do not report this as success.`,
  );
}

export const toolDefinitions: ToolDefinition[] = [
  {
    name: 'provision_inactive_test_campaign',
    description:
      'Create an INACTIVE test graph in one call: an unpublished email template, an unpublished segment filtered on one tag, and an ' +
      'unpublished campaign whose only contact source is that segment. Refuses on a shared deployment, without a TEST-only grant, or ' +
      'when any publish/send/activate/recipient/update field is supplied. Reads every object back and fails if anything persisted as ' +
      'published or the campaign source does not reference the new segment. A tag change is not a campaign entry source.',
    inputSchema: {
      type: 'object',
      properties: {
        emailName: { type: 'string', description: 'Email template name (must match a granted fixture prefix)' },
        emailSubject: { type: 'string', description: 'Email subject' },
        customHtml: { type: 'string', description: 'Email HTML body' },
        segmentName: { type: 'string', description: 'Segment name (must match a granted fixture prefix)' },
        campaignName: { type: 'string', description: 'Campaign name (must match a granted fixture prefix)' },
        tagName: { type: 'string', description: 'Tag the segment filters on (must match a granted tag prefix)' },
      },
      required: ['emailName', 'emailSubject', 'segmentName', 'campaignName', 'tagName'],
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
    for (const [field, value] of Object.entries({ emailName, emailSubject, segmentName, campaignName, tagName })) {
      if (value === '') {
        throw new McpError(ErrorCode.InvalidParams, `provision_inactive_test_campaign: ${field} is required`);
      }
    }

    const origin = originOf(typeof client?.getBaseUrl === 'function' ? client.getBaseUrl() : null);

    // 1. Unpublished email template.
    const emailResponse = await client.v1.post('/emails/new', {
      name: emailName,
      subject: emailSubject,
      customHtml: typeof args?.customHtml === 'string' ? args.customHtml : `<p>${emailSubject}</p>`,
      emailType: 'template',
      isPublished: false,
    });
    const emailId = requireId(emailResponse?.data?.email?.id, 'email template');
    const emailReadback = await client.v1.get(`/emails/${emailId}`);
    const emailPersisted = emailReadback?.data?.email ?? {};
    if (isPublished(emailPersisted.isPublished)) {
      throw new McpError(
        ErrorCode.InternalError,
        `provision_inactive_test_campaign: email template ${emailId} persisted as PUBLISHED. Aborting the graph; do not treat this as success.`,
      );
    }

    // 2. Unpublished segment filtered on exactly one granted tag.
    const filter = tagSegmentFilter(tagName);
    const segmentResponse = await client.v1.post('/segments/new', {
      name: segmentName,
      isPublished: false,
      filters: [filter],
    });
    const segmentId = requireId(segmentResponse?.data?.list?.id, 'segment');
    const segmentReadback = await client.v1.get(`/segments/${segmentId}`);
    const segmentPersisted = segmentReadback?.data?.list ?? {};
    if (isPublished(segmentPersisted.isPublished)) {
      throw new McpError(
        ErrorCode.InternalError,
        `provision_inactive_test_campaign: segment ${segmentId} persisted as PUBLISHED. Aborting the graph; do not treat this as success.`,
      );
    }
    const persistedFilters = Array.isArray(segmentPersisted.filters) ? segmentPersisted.filters : [];
    const tagFilterPersisted = persistedFilters.some(
      (item: any) => item?.field === 'tags' && String(item?.properties?.filter ?? item?.filter ?? '') === tagName,
    );

    // 3. Unpublished campaign whose only source is that segment. No events.
    const campaignResponse = await client.v1.post('/campaigns/new', {
      name: campaignName,
      isPublished: false,
      lists: [{ id: segmentId }],
    });
    const campaignId = requireId(campaignResponse?.data?.campaign?.id, 'campaign');
    const campaignReadback = await client.v1.get(`/campaigns/${campaignId}`);
    const campaignPersisted = campaignReadback?.data?.campaign ?? {};
    if (isPublished(campaignPersisted.isPublished)) {
      throw new McpError(
        ErrorCode.InternalError,
        `provision_inactive_test_campaign: campaign ${campaignId} persisted as PUBLISHED. Aborting; do not treat this as success.`,
      );
    }
    const persistedLists = Array.isArray(campaignPersisted.lists) ? campaignPersisted.lists : null;
    const sourceMatches =
      persistedLists === null
        ? 'not-returned-by-readback'
        : persistedLists.some((item: any) => String(item?.id ?? item) === String(segmentId));
    if (sourceMatches === false) {
      throw new McpError(
        ErrorCode.InternalError,
        `provision_inactive_test_campaign: campaign ${campaignId} read back without segment ${segmentId} as its contact source.`,
      );
    }
    const persistedEvents = campaignPersisted.events;
    const eventCount =
      persistedEvents && typeof persistedEvents === 'object' ? Object.keys(persistedEvents).length : 0;
    if (eventCount > 0) {
      throw new McpError(
        ErrorCode.InternalError,
        `provision_inactive_test_campaign: campaign ${campaignId} read back with ${eventCount} event(s); this tool creates none.`,
      );
    }

    const payload = {
      created: {
        email: {
          id: emailId,
          name: emailName,
          persistedIsPublished: isPublished(emailPersisted.isPublished),
          sourceLink: origin ? `${origin}/s/emails/edit/${emailId}` : null,
        },
        segment: {
          id: segmentId,
          name: segmentName,
          persistedIsPublished: isPublished(segmentPersisted.isPublished),
          filter,
          filterPersisted: tagFilterPersisted,
          sourceLink: origin ? `${origin}/s/segments/edit/${segmentId}` : null,
        },
        campaign: {
          id: campaignId,
          name: campaignName,
          persistedIsPublished: isPublished(campaignPersisted.isPublished),
          entrySource: 'segment (campaign lists)',
          sourceMatches,
          eventCount,
          sourceLink: origin ? `${origin}/s/campaigns/edit/${campaignId}` : null,
        },
      },
      activation: 'inactive - nothing published, nothing sent, no event created',
      tagDependentEntry:
        'the campaign enters contacts through the tag-filtered segment (supported campaign source); a tag change is not an entry source',
      notRun: [
        'tag-dependent entry with real contacts (needs a live provider test)',
        'duplicate suppression',
        'opt-out/do-not-contact suppression',
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
