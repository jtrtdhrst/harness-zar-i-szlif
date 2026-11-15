/**
 * DOD-SEC-01..04 — the write guard must fail closed at the transport boundary
 * (`dispatchTool`), not in a prompt: unknown tool, missing/invalid/expired grant,
 * tenant/host/principal mismatch, out-of-scope resource, or a mutation outside
 * the TEST-only scope must all reach the provider **zero** times.
 *
 * Every negative case asserts the recording client saw no mutating request, and
 * the cases that fail before the identity probe assert no request at all.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import { dispatchTool, allToolDefinitions } from '../build/tools/index.js';
import { TOOL_EFFECTS, WriteGuard } from '../build/security/write-guard.js';
import { McpError } from '../build/errors.js';
import { axiosError, mockClient } from './helpers.mjs';

const HOST = 'mautic.example.pl';
const TENANT = 'zar-i-szlif-test';
const PRINCIPAL = 'lifecycle-ops';
const TAG = 'TEST-ZARI-209-WELCOME';
const SELF_ROUTE = {
  status: 200,
  data: { user: { id: 3, username: PRINCIPAL, email: 'ops@example.invalid' } },
};

function makeGrant(overrides = {}) {
  return JSON.stringify({
    tenant: TENANT,
    tools: ['add_contact_tags', 'create_contact', 'update_contact', 'delete_contact', 'create_tag'],
    allowedTagPrefixes: ['TEST-'],
    allowedContactEmails: ['*@example.invalid'],
    scope: 'test-only',
    expiresAt: '2099-01-01T00:00:00Z',
    ...overrides,
  });
}

function makeEnv(overrides = {}) {
  return {
    MAUTIC_TARGET_HOST: HOST,
    MAUTIC_TARGET_TENANT: TENANT,
    MAUTIC_PRINCIPAL: PRINCIPAL,
    MAUTIC_WRITE_GRANT: makeGrant(),
    ...overrides,
  };
}

function identityClient(extraRoutes = {}, options = {}) {
  return mockClient({
    baseUrl: options.baseUrl ?? `https://${HOST}/api/`,
    accessToken: 'ACCESS-TOKEN-SHOULD-NEVER-LEAK',
    clientSecret: 'CLIENT-SECRET-SHOULD-NEVER-LEAK',
    routes: { 'v1:GET:/users/self': SELF_ROUTE, ...extraRoutes },
  });
}

function mutatingCalls(client) {
  return client.calls.filter((call) => call.method !== 'GET');
}

async function expectDenied(promise, reason) {
  await assert.rejects(promise, (error) => {
    assert.ok(error instanceof McpError, 'denial must be a typed MCP error');
    assert.equal(error.data?.error, 'WRITE_GUARD_DENIED');
    assert.equal(error.data?.reason, reason);
    return true;
  });
}

// ---------------------------------------------------------------- fail closed

test('a read tool passes with no grant at all and issues only a GET', async () => {
  const client = mockClient({ routes: { 'v1:GET:/tags': { status: 200, data: { total: 0, tags: {} } } } });
  const result = await dispatchTool('list_tags', client, {}, new WriteGuard({}));
  assert.match(result.content[0].text, /Found 0 tags/);
  assert.deepEqual(client.calls.map((call) => call.method), ['GET']);
});

test('no grant: every mutating tool is denied and no provider request is made', async () => {
  for (const tool of ['add_contact_tags', 'create_contact', 'update_contact', 'delete_contact', 'create_tag']) {
    const client = mockClient({ routes: {} });
    await expectDenied(dispatchTool(tool, client, { contactId: 2, tags: [TAG], id: 2, email: 'a@example.invalid' }, new WriteGuard({})), 'NO_GRANT');
    assert.equal(client.calls.length, 0, `${tool} must not touch the provider without a grant`);
  }
});

test('direct call with only the identity env but no grant is still denied (no bypass)', async () => {
  const client = identityClient();
  const env = makeEnv({ MAUTIC_WRITE_GRANT: '' });
  await expectDenied(dispatchTool('add_contact_tags', client, { contactId: 2, tags: [TAG] }, new WriteGuard(env)), 'NO_GRANT');
  assert.equal(client.calls.length, 0);
});

test('malformed grant is rejected, not partially honoured', async () => {
  const client = identityClient();
  for (const bad of ['{"tenant":', JSON.stringify({ ...JSON.parse(makeGrant()), scope: 'production' }), '[]']) {
    await expectDenied(
      dispatchTool('add_contact_tags', client, { contactId: 2, tags: [TAG] }, new WriteGuard(makeEnv({ MAUTIC_WRITE_GRANT: bad }))),
      'GRANT_INVALID',
    );
  }
  assert.equal(client.calls.length, 0);
});

test('expired grant writes nothing', async () => {
  const client = identityClient();
  const env = makeEnv({ MAUTIC_WRITE_GRANT: makeGrant({ expiresAt: '2020-01-01T00:00:00Z' }) });
  await expectDenied(dispatchTool('add_contact_tags', client, { contactId: 2, tags: [TAG] }, new WriteGuard(env)), 'GRANT_EXPIRED');
  assert.equal(client.calls.length, 0);
});

test('grant/pinned tenant mismatch writes nothing', async () => {
  const client = identityClient();
  const env = makeEnv({ MAUTIC_TARGET_TENANT: 'another-tenant' });
  await expectDenied(dispatchTool('add_contact_tags', client, { contactId: 2, tags: [TAG] }, new WriteGuard(env)), 'TENANT_MISMATCH');
  assert.equal(client.calls.length, 0);
});

test('configured base host mismatch writes nothing', async () => {
  const client = identityClient({}, { baseUrl: 'https://mautic.other-host.example/api/' });
  await expectDenied(dispatchTool('add_contact_tags', client, { contactId: 2, tags: [TAG] }, new WriteGuard(makeEnv())), 'HOST_MISMATCH');
  assert.equal(mutatingCalls(client).length, 0);
});

test('credential principal mismatch (decided by the provider) writes nothing', async () => {
  const client = identityClient({
    'v1:GET:/users/self': { status: 200, data: { user: { id: 9, username: 'somebody-else', email: 'other@example.invalid' } } },
  });
  await expectDenied(dispatchTool('add_contact_tags', client, { contactId: 2, tags: [TAG] }, new WriteGuard(makeEnv())), 'PRINCIPAL_MISMATCH');
  assert.equal(mutatingCalls(client).length, 0);
});

test('unverifiable identity writes nothing', async () => {
  const failing = identityClient({
    'v1:GET:/users/self': () => {
      throw axiosError(401, {});
    },
  });
  await expectDenied(dispatchTool('add_contact_tags', failing, { contactId: 2, tags: [TAG] }, new WriteGuard(makeEnv())), 'IDENTITY_UNAVAILABLE');
  assert.equal(mutatingCalls(failing).length, 0);

  // A client without a base-URL accessor (e.g. the Cloudflare Worker client) cannot prove the host.
  const noAccessor = mockClient({ routes: { 'v1:GET:/users/self': SELF_ROUTE } });
  delete noAccessor.getBaseUrl;
  await expectDenied(dispatchTool('add_contact_tags', noAccessor, { contactId: 2, tags: [TAG] }, new WriteGuard(makeEnv())), 'IDENTITY_UNAVAILABLE');
  assert.equal(mutatingCalls(noAccessor).length, 0);
});

test('tool missing from the grant allowlist writes nothing', async () => {
  const client = identityClient();
  const env = makeEnv({ MAUTIC_WRITE_GRANT: makeGrant({ tools: ['create_tag'] }) });
  await expectDenied(dispatchTool('add_contact_tags', client, { contactId: 2, tags: [TAG] }, new WriteGuard(env)), 'TOOL_NOT_GRANTED');
  assert.equal(mutatingCalls(client).length, 0);
});

test('unclassified tool name is denied as a mutation', async () => {
  const client = identityClient();
  await expectDenied(dispatchTool('some_future_write_tool', client, {}, new WriteGuard(makeEnv())), 'UNKNOWN_TOOL');
  assert.equal(client.calls.length, 0);
});

// ------------------------------------------------- sending / activation denials

test('send, activation, enrollment and out-of-scope mutations stay denied even when the grant lists them', async () => {
  const listed = [
    'execute_campaign',
    'send_email',
    'send_email_to_segment',
    'add_contact_to_campaign',
    'add_contact_to_segment',
    'create_campaign_with_automation',
    'create_segment',
    'import_campaign',
    'update_project',
  ];
  for (const tool of listed) {
    const client = identityClient();
    const env = makeEnv({ MAUTIC_WRITE_GRANT: makeGrant({ tools: listed }) });
    await expectDenied(dispatchTool(tool, client, { campaignId: 1, emailId: 1, contactId: 2, segmentId: 3 }, new WriteGuard(env)), 'TOOL_DENIED');
    assert.equal(client.calls.length, 0, `${tool} must never reach the provider`);
  }
});

// ------------------------------------------------------------ resource scope

test('tag outside the granted prefix writes nothing', async () => {
  const client = identityClient();
  await expectDenied(
    dispatchTool('add_contact_tags', client, { contactId: 2, tags: ['PROD-CUSTOMER'] }, new WriteGuard(makeEnv())),
    'SCOPE_VIOLATION',
  );
  assert.equal(mutatingCalls(client).length, 0);
});

test('contact outside the granted recipient scope writes nothing', async () => {
  const client = identityClient();
  await expectDenied(
    dispatchTool('create_contact', client, { email: 'real.customer@zariszlif.pl' }, new WriteGuard(makeEnv())),
    'SCOPE_VIOLATION',
  );
  assert.equal(mutatingCalls(client).length, 0);
});

test('deleting a contact whose real email is outside scope writes nothing', async () => {
  const client = identityClient({
    'v1:GET:/contacts/7': { status: 200, data: { contact: { id: 7, email: 'real.customer@zariszlif.pl' } } },
  });
  await expectDenied(dispatchTool('delete_contact', client, { id: 7 }, new WriteGuard(makeEnv())), 'SCOPE_VIOLATION');
  assert.equal(mutatingCalls(client).length, 0);
  assert.deepEqual(client.calls.map((call) => `${call.method} ${call.path}`), ['GET /users/self', 'GET /contacts/7']);
});

// ------------------------------------------------------------------ positives

test('a scoped TEST-only tag write is allowed and returns the provider read-back', async () => {
  const client = identityClient({
    'v1:GET:/contacts/2': {
      status: 200,
      data: { contact: { id: 2, email: 'fixture@example.invalid', tags: [TAG] } },
    },
    'v1:PATCH:/contacts/2/edit': { status: 200, data: { contact: { id: 2 } } },
  });

  const result = await dispatchTool('add_contact_tags', client, { contactId: 2, tags: [TAG] }, new WriteGuard(makeEnv()));

  const written = mutatingCalls(client);
  assert.equal(written.length, 1);
  assert.equal(written[0].method, 'PATCH');
  assert.equal(written[0].path, '/contacts/2/edit');
  assert.deepEqual(written[0].body, { tags: [TAG] });
  assert.match(result.content[0].text, /Tags confirmed on contact 2/);
  // identity was proved at the provider before the write
  assert.equal(client.calls.filter((call) => call.path === '/users/self').length, 1);
});

test('a scoped fixture contact create is allowed', async () => {
  const client = identityClient({
    'v1:POST:/contacts/new': { status: 200, data: { contact: { id: 11, email: 'fixture@example.invalid' } } },
    'v1:GET:/contacts/11': { status: 200, data: { contact: { id: 11, tags: [TAG] } } },
  });

  const result = await dispatchTool(
    'create_contact',
    client,
    { email: 'fixture@example.invalid', customFields: { tags: [TAG] } },
    new WriteGuard(makeEnv()),
  );

  const written = mutatingCalls(client);
  assert.equal(written.length, 1);
  assert.equal(written[0].path, '/contacts/new');
  assert.match(result.content[0].text, /Contact created successfully/);
});

test('the identity probe is cached so a write batch does not re-probe', async () => {
  const client = identityClient({
    'v1:GET:/contacts/2': { status: 200, data: { contact: { id: 2, tags: [TAG] } } },
    'v1:PATCH:/contacts/2/edit': { status: 200, data: { contact: { id: 2 } } },
  });
  const guard = new WriteGuard(makeEnv());
  await dispatchTool('add_contact_tags', client, { contactId: 2, tags: [TAG] }, guard);
  await dispatchTool('add_contact_tags', client, { contactId: 2, tags: [TAG] }, guard);
  assert.equal(client.calls.filter((call) => call.path === '/users/self').length, 1);
});

// ------------------------------------------------------- noise/hygiene checks

test('denials carry a structured, sanitized payload', async () => {
  const client = identityClient();
  const env = makeEnv({ MAUTIC_WRITE_GRANT: makeGrant({ tools: [] }) });
  await assert.rejects(
    () => dispatchTool('add_contact_tags', client, { contactId: 2, tags: [TAG] }, new WriteGuard(env)),
    (error) => {
      const text = `${error.message} ${JSON.stringify(error.data)}`;
      assert.equal(error.data.error, 'WRITE_GUARD_DENIED');
      assert.equal(error.data.tool, 'add_contact_tags');
      assert.equal(error.data.targetHost, HOST);
      assert.doesNotMatch(text, /CLIENT-SECRET-SHOULD-NEVER-LEAK/);
      assert.doesNotMatch(text, /ACCESS-TOKEN-SHOULD-NEVER-LEAK/);
      assert.doesNotMatch(text, /Bearer/i);
      assert.doesNotMatch(text, /allowedTagPrefixes/);
      return true;
    },
  );
});

test('every advertised tool is explicitly classified (no writable-by-default gaps)', () => {
  const advertised = allToolDefinitions.map((definition) => definition.name).sort();
  const classified = Object.keys(TOOL_EFFECTS).sort();
  assert.deepEqual(classified, advertised, 'TOOL_EFFECTS must cover exactly the advertised tool surface');

  for (const definition of allToolDefinitions) {
    const effect = TOOL_EFFECTS[definition.name];
    assert.ok(['read', 'test-write', 'denied'].includes(effect), `${definition.name} must have a known effect`);
  }
});

test('startup summary is non-secret and reports the fail-closed state', () => {
  const withoutGrant = new WriteGuard({});
  assert.match(withoutGrant.describe(), /mode=enforce grant=absent/);
  const withGrant = new WriteGuard(makeEnv());
  const summary = withGrant.describe();
  assert.match(summary, /grant=present/);
  assert.doesNotMatch(summary, /TEST-|allowedTagPrefixes|@example/);
});
