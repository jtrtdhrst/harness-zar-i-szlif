import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import { mkdtempSync, writeFileSync, chmodSync, symlinkSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Client, InMemoryTransport } from '@modelcontextprotocol/client';
import { CoolifyMcpServer } from '../lib/mcp-server.js';
import type { CoolifyClient } from '../lib/coolify-client.js';
import {
  validateCatalog, validatePath, readReleaseCatalog, releaseStatus,
  releasePreflight, releaseDrift, ReleaseRefusal,
} from '../lib/release-ops.js';

const UUID = 'f7smgdueq8frlex9lfhp9iji';
const COMPONENT = '4stkxzxvghaogtvnqpymacll';
const SHA = '1'.repeat(40);
const DIGEST = 'sha256:' + 'a'.repeat(64);
const IMAGE = 'ghcr.io/jtrtdhrst/coolify-mcp@' + DIGEST;
const target = {
  uuid: UUID, kind: 'service' as const, component_uuid: COMPONENT,
  source_sha: SHA, image: IMAGE, promotion: 'auto_main' as const,
};
const catalog = { schema_version: 1, targets: [target] };
let dir: string;
let file: string;
let previousEnable: string | undefined;
let previousCatalog: string | undefined;

function fakeClient(image = IMAGE, status = 'running:healthy') {
  return {
    getService: async () => ({
      uuid: UUID, status,
      applications: [{ uuid: COMPONENT, image, status }],
    }),
  } as unknown as CoolifyClient;
}
function assertRefusal(code: string, fn: () => unknown) {
  expect(fn).toThrow(new ReleaseRefusal(code));
}

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'zis-coolify-release-'));
  file = join(dir, 'catalog.json');
  writeFileSync(file, JSON.stringify(catalog), { mode: 0o600 });
  previousEnable = process.env.COOLIFY_ZIS_RELEASE_TOOLS;
  previousCatalog = process.env.COOLIFY_RELEASE_CATALOG_FILE;
  process.env.COOLIFY_ZIS_RELEASE_TOOLS = 'true';
  process.env.COOLIFY_RELEASE_CATALOG_FILE = file;
});
afterEach(() => {
  if (previousEnable === undefined) delete process.env.COOLIFY_ZIS_RELEASE_TOOLS;
  else process.env.COOLIFY_ZIS_RELEASE_TOOLS = previousEnable;
  if (previousCatalog === undefined) delete process.env.COOLIFY_RELEASE_CATALOG_FILE;
  else process.env.COOLIFY_RELEASE_CATALOG_FILE = previousCatalog;
  rmSync(dir, { recursive: true, force: true });
});

describe('release catalog security: negative cases', () => {
  it('rejects mutable tags, invalid SHA, wrong promotion and duplicate targets', () => {
    assertRefusal('invalid_target', () => validateCatalog({ schema_version: 1, targets: [{ ...target, image: 'ghcr.io/x/y:latest' }] }));
    assertRefusal('invalid_target', () => validateCatalog({ schema_version: 1, targets: [{ ...target, source_sha: 'main' }] }));
    assertRefusal('invalid_target', () => validateCatalog({ schema_version: 1, targets: [{ ...target, promotion: 'override' }] }));
    assertRefusal('duplicate_target', () => validateCatalog({ schema_version: 1, targets: [target, target] }));
  });
  it('rejects path traversal and non-main branch', () => {
    for (const path of ['../secret', 'a/../b', 'a//b', './x', 'a\nfoo']) expect(validatePath(path)).toBe(false);
    assertRefusal('untrusted_branch', () => validateCatalog({ schema_version: 1, targets: [{ ...target, git_branch: 'ci-approved' }] }));
  });
  it('rejects symlinks, group-writable catalog, missing catalog', () => {
    chmodSync(file, 0o666);
    assertRefusal('release_catalog_untrusted_permissions', () => readReleaseCatalog(file));
    chmodSync(file, 0o600);
    symlinkSync(file, join(dir, 'link.json'));
    assertRefusal('release_catalog_untrusted_permissions', () => readReleaseCatalog(join(dir, 'link.json')));
    assertRefusal('release_catalog_missing', () => readReleaseCatalog(join(dir, 'missing.json')));
    assertRefusal('release_catalog_not_mounted', () => readReleaseCatalog('relative.json'));
  });
  it('rejects ambiguous Compose components', async () => {
    const ambiguous = {
      getService: async () => ({
        uuid: UUID, applications: [
          { uuid: COMPONENT, image: IMAGE }, { uuid: 'anothercomponent123456789', image: IMAGE },
        ],
      }),
    } as unknown as CoolifyClient;
    const noComponentCatalog = { schema_version: 1, targets: [{ ...target, component_uuid: undefined }] };
    writeFileSync(file, JSON.stringify(noComponentCatalog));
    await expect(releaseStatus(ambiguous, UUID, file)).rejects.toThrow('compose_component_ambiguous_or_missing');
  });
});

describe('release evidence: never declare production verified without runtime SHA/E2E', () => {
  it('shows CONFIG_MATCH_ONLY_NOT_DONE even when healthy', async () => {
    const status = await releaseStatus(fakeClient(), UUID, file);
    expect(status.status).toBe('CONFIG_MATCH_ONLY_NOT_DONE');
    expect(status.config_matches_catalog).toBe(true);
    expect(status.release_verified).toBe(false);
    expect(status.runtime_source_sha_verified).toBe(false);
    expect(status.production_e2e_verified).toBe(false);
  });
  it('fails closed on wrong digest', async () => {
    const status = await releaseStatus(fakeClient(IMAGE.replace('aaaa', 'bbbb')), UUID, file);
    expect(status.status).toBe('BLOCKED');
    expect(status.blockers).toContain('configured_image_not_pinned_to_approved_digest');
  });
  it('HOLD blocks even when image matches', async () => {
    writeFileSync(file, JSON.stringify({ schema_version: 1, targets: [{ ...target, promotion: 'hold' }] }));
    const status = await releaseStatus(fakeClient(), UUID, file);
    expect(status.blockers).toContain('hold');
  });
  it('preflight refuses unreviewed user-supplied SHA/digest', async () => {
    const wrong = await releasePreflight(fakeClient(), {
      uuid: UUID, source_sha: '2'.repeat(40), image_digest: DIGEST,
    }, file);
    expect(wrong.authorized_to_deploy).toBe(false);
    expect(wrong.blockers).toContain('source_sha_not_in_catalog');
    const matched = await releasePreflight(fakeClient(), {
      uuid: UUID, source_sha: SHA, image_digest: DIGEST,
    }, file);
    expect(matched.authorized_to_deploy).toBe(false);
    expect(matched.blockers).toContain('independent_release_admission_required');
    await expect(releasePreflight(fakeClient(), {
      uuid: UUID, source_sha: SHA, image_digest: 'sha256:latest',
    }, file)).rejects.toThrow('invalid_candidate');
  });
  it('drift scan captures Coolify read errors without marking success', async () => {
    const failing = { getService: async () => { throw new Error('unavailable'); } } as unknown as CoolifyClient;
    const report = await releaseDrift(failing, file);
    expect(report.checked).toBe(1);
    expect(report.all_production_verified).toBe(false);
    expect(report.results[0].status).toBe('BLOCKED');
  });
});

describe('MCP E2E in-memory (real tools/list and tools/call)', () => {
  it('registers five usable release tools and denies deployment authorization', async () => {
    const server = new CoolifyMcpServer({ baseUrl: 'http://localhost:3000', accessToken: 'fixture' });
    // Inject a deterministic Coolify API fixture while keeping the real MCP client transport.
    (server as unknown as { client: { getService: () => Promise<unknown> } }).client.getService =
      async () => ({ uuid: UUID, status: 'running:healthy',
        applications: [{ uuid: COMPONENT, image: IMAGE }] });
    const client = new Client({ name: 'coolify-release-e2e', version: '1.0.0' });
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    try {
      await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);
      const tools = await client.listTools();
      const releaseNames = tools.tools.filter((t) => t.name.startsWith('release_')).map((t) => t.name);
      expect(releaseNames.sort()).toEqual([
        'release_catalog', 'release_drift', 'release_inventory',
        'release_preflight', 'release_status',
      ]);
      const result = await client.callTool({
        name: 'release_preflight',
        arguments: { uuid: UUID, source_sha: SHA, image_digest: DIGEST },
      });
      const value = JSON.parse((result.content[0] as { text: string }).text) as {
        authorized_to_deploy: boolean; status: string;
      };
      expect(value.authorized_to_deploy).toBe(false);
      expect(value.status).toBe('NOT_AUTHORIZED');
    } finally {
      await Promise.all([client.close(), server.close()]);
    }
  });
  it('does not register new tools when opt-in is disabled', async () => {
    delete process.env.COOLIFY_ZIS_RELEASE_TOOLS;
    const server = new CoolifyMcpServer({ baseUrl: 'http://localhost:3000', accessToken: 'fixture' });
    const client = new Client({ name: 'coolify-release-disabled', version: '1.0.0' });
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    try {
      await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);
      const tools = await client.listTools();
      expect(tools.tools.some((t) => t.name.startsWith('release_'))).toBe(false);
    } finally {
      await Promise.all([client.close(), server.close()]);
    }
  });
});
