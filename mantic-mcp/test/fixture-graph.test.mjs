/**
 * SECURITY GATE v2 (owner rework 2026-11-16) — the narrow grantable path for an
 * INACTIVE test graph: unpublished email template + tag-filtered segment +
 * unpublished campaign whose only source is that segment.
 *
 * Rules pinned here:
 *  - the shared stdio/HTTP transport can never create graph objects, even with a
 *    valid grant (no trusted per-agent identity implies no graph creation);
 *  - a dedicated TEST deployment still needs grant + pinned identity + scope;
 *  - publish/send/activate/recipient/update arguments are a denial, not ignored;
 *  - the general create tools stay permanently denied;
 *  - every object is read back, and a published readback is a failure.
 */
import assert from 'node:assert/strict';
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

const ARGS = {
  emailName: `${PREFIX}email`,
  emailSubject: 'Inactive fixture email',
  customHtml: '<p>fixture</p>',
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
    MAUTIC_DEPLOYMENT_CLASS: 'dedicated-test',
    MAUTIC_WRITE_GRANT: JSON.stringify(grant()),
    ...overrides,
  };
}

const SELF = { status: 200, data: { user: { username: PRINCIPAL, email: 'ops@example.invalid' } } };
const EMAIL_CREATED = { status: 200, data: { email: { id: 101 } } };
const EMAIL_READBACK = { status: 200, data: { email: { id: 101, isPublished: false } } };
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
  data: { campaign: { id: 303, isPublished: false, lists: [{ id: 202 }], events: {} } },
};

function client(overrides = {}) {
  return mockClient({
    baseUrl: `https://${HOST}/api/`,
    accessToken: 'ACCESS-TOKEN-SHOULD-NEVER-LEAK',
    clientSecret: 'CLIENT-SECRET-SHOULD-NEVER-LEAK',
    routes: {
      'v1:GET:/users/self': SELF,
      'v1:POST:/emails/new': EMAIL_CREATED,
      'v1:GET:/emails/101': EMAIL_READBACK,
      'v1:POST:/segments/new': SEGMENT_CREATED,
      'v1:GET:/segments/202': SEGMENT_READBACK,
      'v1:POST:/campaigns/new': CAMPAIGN_CREATED,
      'v1:GET:/campaigns/303': CAMPAIGN_READBACK,
      ...overrides,
    },
  });
}

const writes = (c) => c.calls.filter((call) => call.method !== 'GET');

async function expectDenied(promise, reason) {
  await assert.rejects(promise, (error) => {
    assert.ok(error instanceof McpError, 'denial must be a typed MCP error');
    assert.equal(error.data?.error, 'WRITE_GUARD_DENIED');
    assert.equal(error.data?.reason, reason);
    return true;
  });
}

// ------------------------------------------------------------------ positives

test('a dedicated TEST deployment can create the inactive graph, exactly as specified', async () => {
  const c = client();
  const result = await dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env()));

  const posted = c.calls.filter((call) => call.method === 'POST');
  assert.deepEqual(posted.map((call) => call.path), ['/emails/new', '/segments/new', '/campaigns/new']);

  const [email, segment, campaign] = posted.map((call) => call.body);
  assert.equal(email.isPublished, false);
  assert.equal(email.emailType, 'template');
  assert.equal(email.name, ARGS.emailName);
  assert.equal(segment.isPublished, false);
  assert.deepEqual(segment.filters, [
    { glue: 'and', field: 'tags', object: 'lead', type: 'text', operator: 'like', properties: { filter: TAG } },
  ]);
  assert.equal(campaign.isPublished, false);
  assert.deepEqual(campaign.lists, [{ id: 202 }]);
  assert.equal('events' in campaign, false, 'no campaign events may be created');

  // read back every object
  assert.deepEqual(
    c.calls.filter((call) => call.method === 'GET').map((call) => call.path),
    ['/users/self', '/emails/101', '/segments/202', '/campaigns/303'],
  );

  const text = result.content[0].text;
  assert.match(text, /"persistedIsPublished": false/);
  assert.match(text, /https:\/\/mautic\.example\.pl\/s\/campaigns\/edit\/303/);
  assert.match(text, /segment \(campaign lists\)/);
  assert.match(text, /notRun/);

  const payload = JSON.parse(text.slice(text.indexOf('{')));
  assert.equal(payload.created.segment.filterPersisted, true);
  assert.equal(payload.created.campaign.sourceMatches, true);
  assert.equal(payload.created.campaign.eventCount, 0);
  assert.doesNotMatch(text, new RegExp(c.accessToken));
  assert.doesNotMatch(text, /Bearer/i);
});

test('a readback that omits the source list is reported honestly, not as proof', async () => {
  const c = client({
    'v1:GET:/campaigns/303': { status: 200, data: { campaign: { id: 303, isPublished: false } } },
  });
  const result = await dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env()));
  const payload = JSON.parse(result.content[0].text.slice(result.content[0].text.indexOf('{')));
  assert.equal(payload.created.campaign.sourceMatches, 'not-returned-by-readback');
});

// ------------------------------------------------- shared transport is closed

test('the shared transport cannot create a graph even with an otherwise valid grant', async () => {
  for (const deploymentClass of [undefined, '', 'shared']) {
    const c = client();
    await expectDenied(
      dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env({ MAUTIC_DEPLOYMENT_CLASS: deploymentClass }))),
      'SHARED_TRANSPORT_DENIED',
    );
    assert.equal(c.calls.length, 0, 'no provider request may be made on the shared transport');
  }
});

// --------------------------------------------------------------- grant gates

test('no grant, expired grant, wrong tenant, wrong host, wrong principal and unlisted tool all write nothing', async () => {
  const cases = [
    ['NO_GRANT', () => client(), env({ MAUTIC_WRITE_GRANT: '' })],
    ['GRANT_EXPIRED', () => client(), env({ MAUTIC_WRITE_GRANT: JSON.stringify(grant({ expiresAt: '2020-01-01T00:00:00Z' })) })],
    ['TENANT_MISMATCH', () => client(), env({ MAUTIC_TARGET_TENANT: 'another-tenant' })],
    ['HOST_MISMATCH', () => client(), env({ MAUTIC_TARGET_HOST: 'mautic.other.example' })],
    [
      'PRINCIPAL_MISMATCH',
      () => client({ 'v1:GET:/users/self': { status: 200, data: { user: { username: 'someone-else' } } } }),
      env(),
    ],
    ['TOOL_NOT_GRANTED', () => client(), env({ MAUTIC_WRITE_GRANT: JSON.stringify(grant({ tools: ['add_contact_tags'] })) })],
  ];

  for (const [reason, makeClient, guardEnv] of cases) {
    const c = makeClient();
    await expectDenied(
      dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(guardEnv)),
      reason,
    );
    assert.equal(writes(c).length, 0, `${reason} must not write`);
  }
});

test('a client whose identity cannot be proven writes nothing', async () => {
  const c = client({ 'v1:GET:/users/self': () => { throw axiosError(401, {}); } });
  await expectDenied(dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env())), 'IDENTITY_UNAVAILABLE');
  assert.equal(writes(c).length, 0);
});

// ----------------------------------------------------------- scope escapes

test('fixture names and the tag must stay inside the granted prefixes', async () => {
  const cases = [
    { ...ARGS, campaignName: 'PROD-Welcome' },
    { ...ARGS, segmentName: 'PROD-Segment' },
    { ...ARGS, emailName: 'PROD-Email' },
    { ...ARGS, tagName: 'PROD-CUSTOMER-TAG' },
  ];
  for (const args of cases) {
    const c = client();
    await expectDenied(dispatchTool('provision_inactive_test_campaign', c, args, new WriteGuard(env())), 'SCOPE_VIOLATION');
    assert.equal(writes(c).length, 0);
  }
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
    assert.equal(writes(c).length, 0, `${Object.keys(extra)[0]} must not produce a provider mutation`);
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
    assert.equal(c.calls.length, 0, `${tool} must stay denied`);
  }
});

// ------------------------------------------------------------- readback failures

test('a resource that persists published fails the call instead of reporting success', async () => {
  const c = client({ 'v1:GET:/emails/101': { status: 200, data: { email: { id: 101, isPublished: true } } } });
  await assert.rejects(
    () => dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env())),
    /persisted as PUBLISHED/,
  );
  assert.deepEqual(c.calls.filter((call) => call.method === 'POST').map((call) => call.path), ['/emails/new']);
});

test('a campaign that read back without the segment source or with events fails', async () => {
  const wrongSource = client({
    'v1:GET:/campaigns/303': { status: 200, data: { campaign: { id: 303, isPublished: false, lists: [{ id: 999 }], events: {} } } },
  });
  await assert.rejects(
    () => dispatchTool('provision_inactive_test_campaign', wrongSource, ARGS, new WriteGuard(env())),
    /without segment 202 as its contact source/,
  );

  const withEvents = client({
    'v1:GET:/campaigns/303': {
      status: 200,
      data: { campaign: { id: 303, isPublished: false, lists: [{ id: 202 }], events: { 1: { type: 'email.send' } } } },
    },
  });
  await assert.rejects(
    () => dispatchTool('provision_inactive_test_campaign', withEvents, ARGS, new WriteGuard(env())),
    /with 1 event/,
  );
});

test('a created object without an id is a failure, not a silent success', async () => {
  const c = client({ 'v1:POST:/emails/new': { status: 200, data: { email: {} } } });
  await assert.rejects(
    () => dispatchTool('provision_inactive_test_campaign', c, ARGS, new WriteGuard(env())),
    /returned no id/,
  );
});

// ------------------------------------------------------------- surface hygiene

test('the tool advertises only the five fixture arguments', () => {
  const definition = allToolDefinitions.find((item) => item.name === 'provision_inactive_test_campaign');
  assert.ok(definition);
  assert.deepEqual(Object.keys(definition.inputSchema.properties).sort(), [
    'campaignName',
    'customHtml',
    'emailName',
    'emailSubject',
    'segmentName',
    'tagName',
  ].sort());
  assert.equal(definition.description.includes('not a campaign entry source'), true);
});
