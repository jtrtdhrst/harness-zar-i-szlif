/**
 * Helpers that translate MCP tool arguments into the payloads Mautic v1
 * (FOSRestBundle) actually accepts.
 *
 * Two defects motivated this module:
 *  - `customFields` was advertised in tool schemas but never translated, so
 *    every "custom field" write (tags included) was a silent no-op reported as
 *    success;
 *  - tag writes were posted to an invented route
 *    (`/contacts/{id}/contact/add`) that Mautic does not implement.
 *
 * The helpers below are deliberately strict: they either produce a body the
 * provider understands, or a caller-visible error.
 */
import type { MauticApiClient } from '../api/client.js';
import { ErrorCode, McpError } from '../errors.js';

const CUSTOM_FIELDS_KEY = 'customFields';

/**
 * Normalise any Mautic tag representation into a de-duplicated, trimmed list.
 * Accepts `string[]`, `{ tag: string }[]`, a comma-separated string, or the
 * object map some Mautic versions return.
 */
export function normalizeTagList(value: unknown): string[] {
  const collected: string[] = [];

  const pushName = (candidate: unknown) => {
    if (typeof candidate === 'string') {
      collected.push(candidate);
      return;
    }
    if (candidate && typeof candidate === 'object') {
      const tag = (candidate as { tag?: unknown }).tag;
      if (typeof tag === 'string') collected.push(tag);
    }
  };

  if (Array.isArray(value)) {
    value.forEach(pushName);
  } else if (typeof value === 'string') {
    collected.push(...value.split(','));
  } else if (value && typeof value === 'object') {
    Object.values(value as Record<string, unknown>).forEach(pushName);
  }

  const seen = new Set<string>();
  const tags: string[] = [];
  for (const raw of collected) {
    const tag = raw.trim();
    if (!tag || seen.has(tag)) continue;
    seen.add(tag);
    tags.push(tag);
  }
  return tags;
}

/** Union of tag lists, preserving first-seen order. */
export function mergeTagLists(...lists: unknown[]): string[] {
  const seen = new Set<string>();
  const tags: string[] = [];
  for (const list of lists) {
    for (const tag of normalizeTagList(list)) {
      if (seen.has(tag)) continue;
      seen.add(tag);
      tags.push(tag);
    }
  }
  return tags;
}

/**
 * Flatten tool arguments into a Mautic v1 contact body.
 *
 * `customFields` is merged at the top level because that is the shape the
 * provider accepts (Mautic field aliases are top-level contact properties).
 * Explicit top-level arguments win over `customFields` entries, and `tags` is
 * always normalised to a string array.
 */
export function flattenContactPayload(
  args: Record<string, unknown> | undefined | null,
  options: { omit?: string[] } = {},
): Record<string, unknown> {
  const omit = new Set(options.omit ?? []);
  const body: Record<string, unknown> = {};

  const customFields = args?.[CUSTOM_FIELDS_KEY];
  if (customFields && typeof customFields === 'object' && !Array.isArray(customFields)) {
    for (const [key, value] of Object.entries(customFields as Record<string, unknown>)) {
      if (omit.has(key) || value === undefined) continue;
      body[key] = value;
    }
  }

  for (const [key, value] of Object.entries(args ?? {})) {
    if (key === CUSTOM_FIELDS_KEY || omit.has(key) || value === undefined) continue;
    body[key] = value;
  }

  if (Object.prototype.hasOwnProperty.call(body, 'tags')) {
    body.tags = normalizeTagList(body.tags);
  }
  return body;
}

/** Read the tag list a contact currently has, straight from the provider. */
export async function readContactTags(
  client: MauticApiClient,
  contactId: number | string,
): Promise<string[]> {
  const response = await client.v1.get(`/contacts/${contactId}`);
  return normalizeTagList(response?.data?.contact?.tags);
}

/**
 * Confirm a tag write by reading the contact back.
 * Throws instead of reporting success when a requested tag did not persist.
 */
export async function verifyContactTags(
  client: MauticApiClient,
  contactId: number | string,
  expected: string[],
  toolName: string,
): Promise<string[]> {
  const confirmed = await readContactTags(client, contactId);
  const missing = expected.filter((tag) => !confirmed.includes(tag));
  if (missing.length > 0) {
    throw new McpError(
      ErrorCode.InternalError,
      `${toolName}: tag write not confirmed for contact ${contactId}. Read-back is missing: ${missing.join(', ')}. ` +
        'The provider accepted the request but did not persist these tags; do not treat this as success.',
    );
  }
  return confirmed;
}
