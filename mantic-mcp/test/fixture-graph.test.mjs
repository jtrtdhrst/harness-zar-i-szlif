/**
 * SECURITY GATE v2 (owner rework 2026-11-16, CHO review round 4) — the narrow
 * grantable path for an INACTIVE test graph: unpublished email template bound to
 * the pinned ZARI-208 artifact hash + tag-filtered segment + unpublished campaign
 * with exactly one non-executing `email.send` action pointing at that email.
 *
 * Pinned here:
 *  F1 the campaign really carries one email.send action referencing the new email;
 *  F2 no success without positive provider evidence (publication state, tag
 *     filter, source list, event) — missing/unknown is NOT_VERIFIED;
 *  F3 idempotent by exact name, and a failure compensates only ids created by the
 *     invocation (pre-existing resources are never deleted);
 *  F4 the email body is bound to the operator-pinned artifact digest;
 *  plus: shared transport, grant/identity gates, scope escapes and forbidden
 *  arguments all produce zero provider mutations.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';

import { dispatchTool, allToolDefinitions } from '../build/tools/index.js';
import { WriteGuard } from '../build/security/write-guard.js';
import { McpError } from '../build/errors.js';
import { axiosError, mockClient } from './helpers.mjs';

const HOST = 'mautic.example.pl';
const TENANT = 'zar-i-szlif-test';
const PRINCIPAL = 'lifecycle-ops';
const TAG = 'TEST-ZARI-207-WELCOME';
const PREFIX = 'TEST-ZARI-207-';
const HTML = '<p>Inactive fixture creative</p>';
const ARTIFACT = createHash('sha256').update(HTML, 'utf8').digest('hex');
const OTHER_ARTIFACT = createHash('sha256').update('<p>other</p>', 'utf8').digest('hex');

const ARGS = {
  emailName: `${PREFIX}email`,
  emailSubject: 'Inactive fixture email',
  customHtml: HTML,
  artifactSha256: ARTIFACT,
  segmentName: `${PREFIX}segment`,
  campaignName: `${PREFIX}campaign`,
  tagName: TAG,
};

function grant(overrides = {}) {
  return {
    tenant: TENANT,
    tools: ['provision_inactive_test_campaign'],
    allowedTagPrefixes: ['TEST-'],
    allowedContactEmails: ['*@example.invalid'],
    allowedFixturePrefixes: [PREFIX],
    pinnedArtifactSha256: [ARTIFACT],
    testPrincipal: PRINCIPAL,
    scope: 'test-only',
    expiresAt: '2099-01-01T00:00:00Z',
    ...overrides,
  };
}

function env(overrides = {}) {
  return {
    MAUTIC_TARGET_HOST: HOST,
    MAUTIC_TARGET_TENANT: TENANT,
    MAUTIC_PRINCIPAL: PRINCIPAL,
    MAUTIC_TEST_IDENTITY_CLASS: 'isolated-test-principal',
    MAUTIC_WRITE_GRANT: JSON.stringify(grant()),
    ...overrides,
  };
}

const SELF = { status: 200, data: { user: { username: PRINCIPAL, email: 'ops@example.invalid' } } };
const EMPTY = (key) => ({ status: 200, data: { total: 0, [key]: {} } });
const EMAIL_CREATED = { status: 200, data: { email: { id: 101 } } };
const EMAIL_READBACK = { status: 200, data: { email: { id: 101, isPublished: false, customHtml: HTML } } };
const SEGMENT_CREATED = { status: 200, data: { list: { id: 202 } } };
const SEGMENT_READBACK = {
  status: 200,
  data: {
    list: {
      id: 202,
      isPublished: false,
      filters: [{ field: 'tags', object: 'lead', type: 'text', operator: 'like', properties: { filter: TAG } }],
    },
  },
};
const CAMPAIGN_CREATED = { status: 200, data: { campaign: { id: 303 } } };
const CAMPAIGN_READBACK = {
  status: 200,
  data: {
    campaign: {
      id: 303,
      isPublished: false,
      lists: [{ id: 202 }],
      events: { 11: { id: 11, type: 'email.send', eventType: 'action', properties: { email: 101 } } },
    },
  },
};

function client(overrides = {}) {
  return mockClient({
    baseUrl: `https://${HOST}/api/`,
    accessToken: 'ACCESS-TOKEN-SHOULD-NEVER-LEAK',
    clientSecret: 'CLIENT-SECRET-SHOULD-NEVER-LEAK',
    routes: {
      'v1:GET:/users/self': SELF,
      'v1:GET:/emails': EMPTY('emails'),
      'v1:GET:/segments': EMPTY('lists'),
      'v1:GET:/campaigns': EMPTY('campaigns'),
      'v1:POST:/emails/new': EMAIL_CREATED,
      'v1:GET:/emails/101': EMAIL_READBACK,
      'v1:POST:/segments/new': SEGMENT_CREATED,
      'v1:GET:/segments/202': SEGMENT_READBACK,
      'v1:POST:/campaigns/new': CAMPAIGN_CREATED,
      'v1:GET:/campaigns/303': CAMPAIGN_READBACK,
      'v1:DELETE:/emails/101/delete': { status: 200, data: {} },
      'v1:DELETE:/segments/202/delete': { status: 200, data: {} },
      'v1:DELETE:/campaigns/303/delete': { status: 200, data: {} },
      ...overrides,
    },
  });
}

const writes = (c) => c.calls.filter((call) => call.method !== 'GET');
const posts = (c) => c.calls.filter((call) => call.method === 'POST');
const deletes = (c) => c.calls.filter((call) => call.method === 'DELETE');

async function expectDenied(promise, reason) {
  await assert.rejects(promise, (error) => {
    assert.ok(error instanceof McpError, 'denial must be a typed MCP error');
    assert.equal(error.data?.error, 'WRITE_GUARD_DENIED');
    assert.equal(error.data?.reason, reason);
    return true;
  });
}

async function expectNotVerified(promise, pattern) {
  await assert.rejects(promise, (error) => {
    assert.ok(error instanceof McpError);
    assert.equal(error.data?.error, 'NOT_VERIFIED');
    assert.match(error.message, /NOT_VERIFIED/);
    if (pattern) assert.match(error.message, pattern);
    return true;
  });
}

// ------------------------------------------------------------------ positives

test('a dedicated TEST deployment creates the full inactive graph including one email.send action', async () => {
  const c = client();
  const result = await dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env()));

  assert.deepEqual(posts(c).map((call) => call.path), ['/emails/new', '/segments/new', '/campaigns/new']);
  const [email, segment, campaign] = posts(c).map((call) => call.body);
  assert.equal(email.isPublished, false);
  assert.equal(email.emailType, 'template');
  assert.equal(email.customHtml, HTML);
  assert.equal(segment.isPublished, false);
  assert.deepEqual(segment.filters, [
    { glue: 'and', field: 'tags', object: 'lead', type: 'text', operator: 'like', properties: { filter: TAG } },
  ]);
  assert.equal(campaign.isPublished, false);
  assert.deepEqual(campaign.lists, [{ id: 202 }]);
  assert.deepEqual(campaign.events, [
    {
      id: 'new1',
      name: `${ARGS.campaignName} (inactive email action)`,
      type: 'email.send',
      eventType: 'action',
      order: 1,
      properties: { email: 101 },
      triggerMode: 'immediate',
    },
  ]);

  const text = result.content[0].text;
  const payload = JSON.parse(text.slice(text.indexOf('{')));
  assert.equal(payload.provisioned, true);
  assert.equal(payload.artifact.sha256, ARTIFACT);
  assert.equal(payload.created.email.persistedIsPublished, false);
  assert.equal(payload.created.segment.persistedIsPublished, false);
  assert.equal(payload.created.segment.filterPersisted, true);
  assert.equal(payload.created.campaign.persistedIsPublished, false);
  assert.equal(payload.created.campaign.sourceMatches, true);
  assert.deepEqual(payload.created.campaign.events, [{ type: 'email.send', emailId: 101 }]);
  assert.match(text, /inactive/);
  assert.doesNotMatch(text, new RegExp(c.accessToken));
  assert.equal(deletes(c).length, 0, 'a successful graph must not be compensated');
});

// ------------------------------------------------- shared transport is closed

test('the shared transport cannot create a graph even with an otherwise valid grant', async () => {
  for (const identityClass of [undefined, '', 'shared', 'dedicated-test']) {
    const c = client();
    await expectDenied(
      dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env({ MAUTIC_TEST_IDENTITY_CLASS: identityClass }))),
      'SHARED_TRANSPORT_DENIED',
    );
    assert.equal(c.calls.length, 0);
  }
});

test('a grant that does not name the pinned principal cannot enable graph creation', async () => {
  for (const testPrincipal of ['', 'someone-else']) {
    const c = client();
    await expectDenied(
      dispatchTool(
        'provision_inactive_test_campaign',
        c,
        ARGS,
        new WriteGuard(env({ MAUTIC_WRITE_GRANT: JSON.stringify(grant({ testPrincipal })) })),
      ),
      'PRINCIPAL_MISMATCH',
    );
    assert.equal(writes(c).length, 0);
  }
});

// --------------------------------------------------------------- grant gates

test('no grant, expired grant, wrong tenant, wrong host, wrong principal and unlisted tool all write nothing', async () => {
  const cases = [
    ['NO_GRANT', () => client(), env({ MAUTIC_WRITE_GRANT: '' })],
    ['GRANT_EXPIRED', () => client(), env({ MAUTIC_WRITE_GRANT: JSON.stringify(grant({ expiresAt: '2020-01-01T00:00:00Z' })) })],
    ['TENANT_MISMATCH', () => client(), env({ MAUTIC_TARGET_TENANT: 'another-tenant' })],
    ['HOST_MISMATCH', () => client(), env({ MAUTIC_TARGET_HOST: 'mautic.other.example' })],
    ['PRINCIPAL_MISMATCH', () => client({ 'v1:GET:/users/self': { status: 200, data: { user: { username: 'someone-else' } } } }), env()],
    ['TOOL_NOT_GRANTED', () => client(), env({ MAUTIC_WRITE_GRANT: JSON.stringify(grant({ tools: ['add_contact_tags'] })) })],
  ];
  for (const [reason, makeClient, guardEnv] of cases) {
    const c = makeClient();
    await expectDenied(dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(guardEnv)), reason);
    assert.equal(writes(c).length, 0, `${reason} must not write`);
  }
});

test('unverifiable identity writes nothing', async () => {
  const c = client({ 'v1:GET:/users/self': () => { throw axiosError(401, {}); } });
  await expectDenied(dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env())), 'IDENTITY_UNAVAILABLE');
  assert.equal(writes(c).length, 0);
});

// ----------------------------------------------------------- scope escapes

test('fixture names, tag and artifact must stay inside the granted scope', async () => {
  const cases = [
    { ...ARGS, campaignName: 'PROD-Welcome' },
    { ...ARGS, segmentName: 'PROD-Segment' },
    { ...ARGS, emailName: 'PROD-Email' },
    { ...ARGS, tagName: 'PROD-CUSTOMER-TAG' },
    { ...ARGS, artifactSha256: OTHER_ARTIFACT, customHtml: '<p>other</p>' },
    { ...ARGS, artifactSha256: 'not-a-hash' },
  ];
  for (const args of cases) {
    const c = client();
    await expectDenied(dispatchTool('provision_inactive_test_campaign', c, args, new WriteGuard(env())), 'SCOPE_VIOLATION');
    assert.equal(writes(c).length, 0);
  }
  // A grant without a pinned artifact can never authorize the tool.
  const unpinned = client();
  await expectDenied(
    dispatchTool(
      'provision_inactive_test_campaign',
      unpinned,
      ARGS,
      new WriteGuard(env({ MAUTIC_WRITE_GRANT: JSON.stringify(grant({ pinnedArtifactSha256: [] })) })),
    ),
    'SCOPE_VIOLATION',
  );
  assert.equal(unpinned.calls.filter((call) => call.method !== 'GET').length, 0);
});

test('publish, send, activate, recipient, event and update arguments are denied before any mutation', async () => {
  const forbidden = [
    { isPublished: true },
    { publishUp: '2026-01-01 00:00:00' },
    { events: [{ type: 'email.send' }] },
    { lists: [{ id: 1 }] },
    { contactIds: [5] },
    { recipients: ['real.customer@zariszlif.pl'] },
    { send: true },
    { activate: true },
    { id: 999 },
    { emailId: 5 },
    { campaignId: 7 },
    { segmentId: 9 },
  ];
  for (const extra of forbidden) {
    const c = client();
    await expectDenied(
      dispatchTool('provision_inactive_test_campaign', c, { ...ARGS, ...extra }, new WriteGuard(env())),
      'SCOPE_VIOLATION',
    );
    assert.equal(writes(c).length, 0);
  }
});

// --------------------------------------------------------- general tools stay shut

test('the general create tools remain permanently denied even on a dedicated TEST deployment', async () => {
  const listed = grant({
    tools: ['create_email_template', 'create_segment', 'create_campaign', 'create_campaign_with_automation', 'execute_campaign', 'send_email'],
  });
  for (const tool of ['create_email_template', 'create_segment', 'create_campaign', 'create_campaign_with_automation', 'execute_campaign', 'send_email']) {
    const c = client();
    await expectDenied(
      dispatchTool(tool, c, { name: `${PREFIX}x` }, new WriteGuard(env({ MAUTIC_WRITE_GRANT: JSON.stringify(listed) }))),
      'TOOL_DENIED',
    );
    assert.equal(c.calls.length, 0);
  }
});

// ------------------------------------------------------- F2: fail-closed readback

test('missing or unknown publication state is NOT_VERIFIED for every resource', async () => {
  const cases = [
    ['email', { 'v1:GET:/emails/101': { status: 200, data: { email: { id: 101 } } } }],
    ['segment', { 'v1:GET:/segments/202': { status: 200, data: { list: { id: 202, filters: SEGMENT_READBACK.data.list.filters } } } }],
    [
      'campaign',
      { 'v1:GET:/campaigns/303': { status: 200, data: { campaign: { id: 303, lists: [{ id: 202 }] } } } },
    ],
  ];
  for (const [label, routes] of cases) {
    const c = client(routes);
    await expectNotVerified(dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env())), /publication state/);
    assert.ok(deletes(c).length > 0, `${label}: created resources must be compensated`);
  }
});

test('a tag filter that did not persist is NOT_VERIFIED', async () => {
  const c = client({
    'v1:GET:/segments/202': { status: 200, data: { list: { id: 202, isPublished: false, filters: [] } } },
  });
  await expectNotVerified(dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env())), /without the tag filter/);
  assert.deepEqual(deletes(c).map((call) => call.path), ['/segments/202/delete', '/emails/101/delete']);
});

test('a campaign readback without a source list is NOT_VERIFIED, never "assumed"', async () => {
  const c = client({
    'v1:GET:/campaigns/303': {
      status: 200,
      data: { campaign: { id: 303, isPublished: false, events: CAMPAIGN_READBACK.data.campaign.events } },
    },
  });
  await expectNotVerified(dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env())), /without its contact source list/);
  assert.deepEqual(deletes(c).map((call) => call.path), ['/campaigns/303/delete', '/segments/202/delete', '/emails/101/delete']);
});

test('a campaign source that does not reference the segment, or a wrong event, is NOT_VERIFIED', async () => {
  const wrongSource = client({
    'v1:GET:/campaigns/303': {
      status: 200,
      data: { campaign: { id: 303, isPublished: false, lists: [{ id: 999 }], events: CAMPAIGN_READBACK.data.campaign.events } },
    },
  });
  await expectNotVerified(
    dispatchTool('provision_inactive_test_campaign', wrongSource, ARGS, new WriteGuard(env())),
    /does not list segment 202/,
  );

  const noEvent = client({
    'v1:GET:/campaigns/303': { status: 200, data: { campaign: { id: 303, isPublished: false, lists: [{ id: 202 }], events: {} } } },
  });
  await expectNotVerified(dispatchTool('provision_inactive_test_campaign', noEvent, ARGS, new WriteGuard(env())), /exactly one email.send action/);

  const wrongEventEmail = client({
    'v1:GET:/campaigns/303': {
      status: 200,
      data: {
        campaign: {
          id: 303,
          isPublished: false,
          lists: [{ id: 202 }],
          events: { 11: { type: 'email.send', properties: { email: 999 } } },
        },
      },
    },
  });
  await expectNotVerified(
    dispatchTool('provision_inactive_test_campaign', wrongEventEmail, ARGS, new WriteGuard(env())),
    /does not reference email 101/,
  );
});

// ------------------------------------------------------- F4: artifact binding

test('the tool refuses a body that does not match the claimed artifact', async () => {
  const c = client();
  await assert.rejects(
    () =>
      dispatchTool(
        'provision_inactive_test_campaign',
        c,
        { ...ARGS, customHtml: '<p>tampered</p>' },
        new WriteGuard(env()),
      ),
    (error) => {
      assert.equal(error.data?.error, 'ARTIFACT_MISMATCH');
      return true;
    },
  );
  assert.equal(c.calls.filter((call) => call.method !== 'GET').length, 0);
});

test('the persisted body must itself be the pinned artifact (CTO review input)', async () => {
  // provider omits the persisted body -> cannot be verified
  const missing = client({
    'v1:GET:/emails/101': { status: 200, data: { email: { id: 101, isPublished: false } } },
  });
  await expectNotVerified(
    dispatchTool('provision_inactive_test_campaign', missing, ARGS, new WriteGuard(env())),
    /without its persisted body/,
  );
  assert.deepEqual(deletes(missing).map((call) => call.path), ['/emails/101/delete']);

  // provider persists a different body than the one we sent (and claimed)
  const drifted = client({
    'v1:GET:/emails/101': { status: 200, data: { email: { id: 101, isPublished: false, customHtml: '<p>drifted</p>' } } },
  });
  await expectNotVerified(
    dispatchTool('provision_inactive_test_campaign', drifted, ARGS, new WriteGuard(env())),
    /does not hash to the pinned artifact/,
  );
  assert.deepEqual(deletes(drifted).map((call) => call.path), ['/emails/101/delete']);
});

test('an inconclusive name lookup fails closed instead of creating a duplicate (CTO review input)', async () => {
  const cases = [
    ['search error', { 'v1:GET:/emails': () => { throw axiosError(503, {}); } }],
    ['empty collection', { 'v1:GET:/emails': { status: 200, data: { total: 0 } } }],
  ];
  for (const [label, routes] of cases) {
    const c = client(routes);
    await expectNotVerified(
      dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env())),
      /refusing to create blind/,
    );
    assert.equal(posts(c).length, 0, `${label} must not create anything`);
    assert.equal(writes(c).length, 0, `${label} must not mutate the provider`);
  }
});

// ------------------------------------------------- F3: idempotency + compensation

test('a retry reuses existing fixtures by exact name instead of duplicating them', async () => {
  const c = client({
    'v1:GET:/emails': { status: 200, data: { total: 1, emails: { 101: { id: 101, name: ARGS.emailName } } } },
    'v1:GET:/segments': { status: 200, data: { total: 1, lists: { 202: { id: 202, name: ARGS.segmentName } } } },
    'v1:GET:/campaigns': { status: 200, data: { total: 1, campaigns: { 303: { id: 303, name: ARGS.campaignName } } } },
  });

  const result = await dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env()));
  assert.equal(posts(c).length, 0, 'no duplicate objects may be created on retry');
  const payload = JSON.parse(result.content[0].text.slice(result.content[0].text.indexOf('{')));
  assert.equal(payload.created.email.reused, true);
  assert.equal(payload.created.segment.reused, true);
  assert.equal(payload.created.campaign.reused, true);
  assert.equal(deletes(c).length, 0);
});

test('a failure after the email create compensates only that email', async () => {
  const c = client({ 'v1:POST:/segments/new': () => { throw axiosError(500, {}); } });
  await expectNotVerified(dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env())), /segment creation failed/);
  assert.deepEqual(deletes(c).map((call) => call.path), ['/emails/101/delete']);
});

test('a failure after the segment create compensates segment then email, and never a pre-existing object', async () => {
  const c = client({
    'v1:GET:/emails': { status: 200, data: { total: 1, emails: { 55: { id: 55, name: ARGS.emailName } } } },
    'v1:GET:/emails/55': { status: 200, data: { email: { id: 55, isPublished: false, customHtml: HTML } } },
    'v1:POST:/campaigns/new': () => { throw axiosError(500, {}); },
  });
  await expectNotVerified(dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env())), /campaign creation failed/);
  assert.deepEqual(deletes(c).map((call) => call.path), ['/segments/202/delete']);
  const deleted = JSON.stringify(deletes(c).map((call) => call.path));
  assert.equal(deleted.includes('/emails/55'), false, 'a reused (pre-existing) email must never be deleted');
});

test('a provider that refuses compensation is reported, not hidden', async () => {
  const c = client({
    'v1:POST:/segments/new': () => { throw axiosError(500, {}); },
    'v1:DELETE:/emails/101/delete': () => { throw axiosError(500, {}); },
  });
  await assert.rejects(
    () => dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env())),
    (error) => {
      assert.equal(error.data?.error, 'NOT_VERIFIED');
      assert.deepEqual(error.data.compensation.failed, ['email:101']);
      return true;
    },
  );
});

// ------------------------------------------------------------- surface hygiene

test('the tool advertises only the seven fixture arguments', () => {
  const definition = allToolDefinitions.find((item) => item.name === 'provision_inactive_test_campaign');
  assert.ok(definition);
  assert.deepEqual(Object.keys(definition.inputSchema.properties).sort(), [
    'artifactSha256',
    'campaignName',
    'customHtml',
    'emailName',
    'emailSubject',
    'segmentName',
    'tagName',
  ].sort());
  assert.match(definition.description, /not a\s+campaign entry source|not a campaign entry source/i);
});
