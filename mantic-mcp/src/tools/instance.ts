/**
 * `get_instance_identity` — read-only proof of *which* Mautic instance a
 * credential talks to.
 *
 * Lifecycle Ops could not distinguish the intended host/tenant from an empty
 * database and stock field lists, and the tool surface exposed no identity at
 * all. This tool answers that from documented endpoints only:
 *   - `GET /users/self` (Mautic v1, documented) → credential identity;
 *   - `GET /api/v2` (API Platform entrypoint) → whether the v2 surface exists.
 *
 * Mautic v1 exposes no version endpoint, so `mauticVersion` stays null unless a
 * probe actually returns one: the tool never invents a version, and it never
 * returns tokens, headers or credential values.
 */
import axios from 'axios';
import type { MauticApiClient } from '../api/client.js';
import type { ToolDefinition, ToolHandler } from '../types/index.js';

interface ProbeOutcome {
  ok: boolean;
  status: number | null;
  error?: string;
  data?: unknown;
}

/**
 * The stdio client exposes `getBaseUrl()`; other hosts (Cloudflare Worker) may
 * not, so identity degrades to "unknown" instead of throwing.
 */
function configuredBaseUrl(client: any): string | null {
  if (typeof client?.getBaseUrl === 'function') {
    const value = client.getBaseUrl();
    return typeof value === 'string' && value !== '' ? value : null;
  }
  if (typeof client?.baseUrl === 'string') return client.baseUrl;
  return null;
}

function hostOf(baseUrl: string | null): { host: string | null; scheme: string | null } {
  if (!baseUrl) return { host: null, scheme: null };
  try {
    const url = new URL(baseUrl);
    return { host: url.host, scheme: url.protocol.replace(':', '') };
  } catch {
    return { host: baseUrl, scheme: null };
  }
}

async function probe(run: () => Promise<any>): Promise<ProbeOutcome> {
  try {
    const response = await run();
    return { ok: true, status: response?.status ?? 200, data: response?.data };
  } catch (error) {
    if (axios.isAxiosError(error)) {
      return {
        ok: false,
        status: error.response?.status ?? null,
        error: error.response?.status
          ? `provider answered HTTP ${error.response.status}`
          : 'provider unreachable',
      };
    }
    return { ok: false, status: null, error: error instanceof Error ? error.message : String(error) };
  }
}

/** Reduce `GET /users/self` to non-secret identity fields. */
function credentialIdentity(data: any): Record<string, unknown> {
  const user = data?.user ?? data ?? {};
  const identity: Record<string, unknown> = {};
  if (user.id !== undefined) identity.id = user.id;
  if (user.username !== undefined) identity.username = user.username;
  if (user.email !== undefined) identity.email = user.email;
  if (user.firstName !== undefined) identity.firstName = user.firstName;
  if (user.lastName !== undefined) identity.lastName = user.lastName;
  const role = user.role?.name ?? user.role;
  if (typeof role === 'string') identity.role = role;
  return identity;
}

export const toolDefinitions: ToolDefinition[] = [
  {
    name: 'get_instance_identity',
    description:
      'Read-only identity check for the Mautic instance behind this MCP: configured base host, the credential ' +
      'identity returned by GET /users/self, and whether the API Platform v2 surface answers. Returns no tokens, ' +
      'headers or credential values. Run it before any write canary to prove which instance was hit.',
    inputSchema: { type: 'object', properties: {} },
  },
];

export const toolHandlers: Record<string, ToolHandler> = {
  async get_instance_identity(client: any, _args: any) {
    const baseUrl = configuredBaseUrl(client);
    const { host, scheme } = hostOf(baseUrl);

    const selfProbe = await probe(() => client.v1.get('/users/self'));
    const v2Probe = await probe(() => client.v2.get(''));

    const identity: Record<string, unknown> = {
      baseHost: host,
      baseScheme: scheme,
      credential: selfProbe.ok
        ? credentialIdentity(selfProbe.data)
        : { available: false, status: selfProbe.status, error: selfProbe.error },
      apiV2: v2Probe.ok
        ? { available: true, status: v2Probe.status }
        : { available: false, status: v2Probe.status, error: v2Probe.error },
      mauticVersion: null,
      versionNote:
        'Mautic v1 (FOSRestBundle) exposes no version endpoint and the API Platform v2 entrypoint carries no ' +
        'version, so identity is the credential-level proof of which instance answered.',
    };

    return {
      content: [
        {
          type: 'text',
          text: `Mautic instance identity:\n${JSON.stringify(identity, null, 2)}`,
        },
      ],
    };
  },
};
