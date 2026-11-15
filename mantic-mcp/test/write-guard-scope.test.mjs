/**
 * ZARI-113 review round 2 — the two bypasses CTO found at `4b949d9`, plus the
 * sibling path the same defect class exposed.
 *
 * F1: `update_contact` compared only the *requested* e-mail, so a TEST-only
 *     grant could rewrite any real contact (including moving its address).
 * F2: the guard extracted tags with its own string-only reader while the
 *     payload builder also accepts `{tag}` objects, so an out-of-scope tag
 *     reached the provider unnormalised.
 * F1-sibling: `add_contact_tags` scoped the tag name but never the target
 *     contact, so a TEST- tag could be written onto a real customer.
 *
 * Every negative asserts zero provider mutations; positives assert the exact
 * body the provider receives, computed by the same normalisation the handler uses.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import { dispatchTool } from '../build/tools/index.js';
import { WriteGuard } from '../build/security/write-guard.js';
import { normalizeTagList } from '../build/lib/contact-payload.js';
import { McpError } from '../build/errors.js';
import { axiosError, mockClient } from './helpers.mjs';

const HOST = 'mautic.example.pl';
const TENANT = 'zar-i-szlif-test';
const PRINCIPAL = 'lifecycle-ops';
const TAG = 'TEST-ZARI-209-WELCOME';
const FIXTURE_EMAIL = 'fixture@example.invalid';
const REAL_EMAIL = 'real.customer@zariszlif.pl';

const ENV = {
  MAUTIC_TARGET_HOST: HOST,
  MAUTIC_TARGET_TENANT: TENANT,
  MAUTIC_PRINCIPAL: PRINCIPAL,
  MAUTIC_WRITE_GRANT: JSON.stringify({
    tenant: TENANT,
    tools: ['add_contact_tags', 'create_contact', 'update_contact', 'delete_contact', 'create_tag'],
    allowedTagPrefixes: ['TEST-'],
    allowedContactEmails: ['*@example.invalid'],
    scope: 'test-only',
    expiresAt: '2099-01-01T00:00:00Z',
  }),
};

const SELF = { status: 200, data: { user: { username: PRINCIPAL, email: 'ops@example.invalid' } } };

function client(extraRoutes = {}) {
  return mockClient({
    baseUrl: `https://${HOST}/api/`,
    routes: { 'v1:GET:/users/self': SELF, ...extraRoutes },
  });
}

const realContact = { status: 200, data: { contact: { id: 999, email: REAL_EMAIL, tags: [] } } };
const fixtureContact = { status: 200, data: { contact: { id: 2, email: FIXTURE_EMAIL, tags: [TAG] } } };
const patchOk = { status: 200, data: { contact: { id: 2 } } };

function writes(c) {
  return c.calls.filter((call) => call.method !== 'GET');
}

async function expectDenied(promise, reason) {
  await assert.rejects(promise, (error) => {
    assert.ok(error instanceof McpError);
    assert.equal(error.data?.error, 'WRITE_GUARD_DENIED');
    assert.equal(error.data?.reason, reason);
    return true;
  });
}

// ---------------------------------------------------------------- F1: target

test('F1: update_contact whose target contact is a real customer is denied, whatever the requested e-mail', async () => {
  for (const args of [
    { id: 999, email: FIXTURE_EMAIL }, // the bypass CTO reported
    { id: 999, firstName: 'overwritten' }, // no e-mail argument at all
    { id: 999, customFields: { tags: [TAG] } }, // tag-only write onto a real contact
  ]) {
    const c = client({ 'v1:GET:/contacts/999': realContact, 'v1:PATCH:/contacts/999/edit': patchOk });
    await expectDenied(dispatchTool('update_contact', c, args, new WriteGuard(ENV)), 'SCOPE_VIOLATION');
    assert.equal(writes(c).length, 0, 'no PATCH may reach the provider');
    assert.ok(
      c.calls.some((call) => call.method === 'GET' && call.path === '/contacts/999'),
      'the guard must resolve the target contact at the provider',
    );
  }
});

test('F1: an unreadable target contact is a denial, not a pass', async () => {
  const c = client({
    'v1:GET:/contacts/999': () => {
      throw axiosError(404, {});
    },
  });
  await expectDenied(dispatchTool('update_contact', c, { id: 999, firstName: 'x' }, new WriteGuard(ENV)), 'SCOPE_VIOLATION');
  assert.equal(writes(c).length, 0);
});

test('F1: a target contact without a verifiable e-mail is a denial', async () => {
  for (const contact of [{ id: 999 }, { id: 999, email: '' }, { id: 999, email: null }]) {
    const c = client({ 'v1:GET:/contacts/999': { status: 200, data: { contact } } });
    await expectDenied(dispatchTool('update_contact', c, { id: 999, firstName: 'x' }, new WriteGuard(ENV)), 'SCOPE_VIOLATION');
    assert.equal(writes(c).length, 0);
  }
});

test('F1: a fixture contact cannot be moved onto a real address', async () => {
  const c = client({ 'v1:GET:/contacts/2': fixtureContact, 'v1:PATCH:/contacts/2/edit': patchOk });
  await expectDenied(
    dispatchTool('update_contact', c, { id: 2, email: REAL_EMAIL }, new WriteGuard(ENV)),
    'SCOPE_VIOLATION',
  );
  assert.equal(writes(c).length, 0);
});

test('F1-sibling: add_contact_tags cannot touch a real customer contact', async () => {
  const c = client({
    'v1:GET:/contacts/999': realContact,
    'v1:PATCH:/contacts/999/edit': { status: 200, data: { contact: { id: 999 } } },
  });
  await expectDenied(dispatchTool('add_contact_tags', c, { contactId: 999, tags: [TAG] }, new WriteGuard(ENV)), 'SCOPE_VIOLATION');
  assert.equal(writes(c).length, 0);
});

test('F1: an in-scope fixture update is still allowed, with the target resolved first', async () => {
  const c = client({
    'v1:GET:/contacts/2': { status: 200, data: { contact: { id: 2, email: FIXTURE_EMAIL, tags: [TAG] } } },
    'v1:PATCH:/contacts/2/edit': patchOk,
  });
  const result = await dispatchTool('update_contact', c, { id: 2, email: FIXTURE_EMAIL, firstName: 'Fixture' }, new WriteGuard(ENV));

  const written = writes(c);
  assert.equal(written.length, 1);
  assert.equal(written[0].path, '/contacts/2/edit');
  assert.deepEqual(written[0].body, { email: FIXTURE_EMAIL, firstName: 'Fixture' });
  assert.match(result.content[0].text, /Contact updated successfully/);
});

// ------------------------------------------------------- F2: tag normalisation

const OBJECT_FORM = [{ tag: 'PROD-CUSTOMER-TAG' }];
const STRING_FORM = ['PROD-CUSTOMER-TAG'];
const COMMA_FORM = 'PROD-CUSTOMER-TAG';
const MAP_FORM = { 'PROD-CUSTOMER-TAG': 'PROD-CUSTOMER-TAG' };

test('F2: every accepted tag representation is scope-checked on create_contact', async () => {
  const representations = [
    ['array of strings', STRING_FORM],
    ['array of {tag} objects', OBJECT_FORM],
    ['comma-separated string', COMMA_FORM],
    ['object map', MAP_FORM],
  ];

  for (const [label, tags] of representations) {
    const c = client({
      'v1:POST:/contacts/new': { status: 200, data: { contact: { id: 1001, email: FIXTURE_EMAIL } } },
    });
    await expectDenied(
      dispatchTool('create_contact', c, { email: FIXTURE_EMAIL, customFields: { tags } }, new WriteGuard(ENV)),
      'SCOPE_VIOLATION',
    );
    assert.equal(writes(c).length, 0, `${label} must not reach the provider`);
  }
});

test('F2: every accepted tag representation is scope-checked on update_contact and add_contact_tags', async () => {
  const representations = [
    ['array of {tag} objects', OBJECT_FORM],
    ['object map', MAP_FORM],
    ['comma-separated string', COMMA_FORM],
  ];

  for (const [label, tags] of representations) {
    const c1 = client({ 'v1:GET:/contacts/2': fixtureContact, 'v1:PATCH:/contacts/2/edit': patchOk });
    await expectDenied(
      dispatchTool('update_contact', c1, { id: 2, customFields: { tags } }, new WriteGuard(ENV)),
      'SCOPE_VIOLATION',
    );
    assert.equal(writes(c1).length, 0, `update_contact ${label} must not reach the provider`);

    const c2 = client({ 'v1:GET:/contacts/2': fixtureContact, 'v1:PATCH:/contacts/2/edit': patchOk });
    await expectDenied(
      dispatchTool('add_contact_tags', c2, { contactId: 2, tags }, new WriteGuard(ENV)),
      'SCOPE_VIOLATION',
    );
    assert.equal(writes(c2).length, 0, `add_contact_tags ${label} must not reach the provider`);
  }
});

test('F2: the guard decides on exactly the tag set the payload builder sends', async () => {
  // Allowed representation in object form: the provider must receive the same
  // normalised list the guard evaluated, never the raw input.
  const c = client({
    'v1:POST:/contacts/new': { status: 200, data: { contact: { id: 1002, email: FIXTURE_EMAIL } } },
    'v1:GET:/contacts/1002': { status: 200, data: { contact: { id: 1002, tags: [TAG] } } },
  });
  await dispatchTool(
    'create_contact',
    c,
    { email: FIXTURE_EMAIL, customFields: { tags: [{ tag: TAG }, ' TEST-ZARI-209-WELCOME '] } },
    new WriteGuard(ENV),
  );

  const [created] = writes(c);
  assert.deepEqual(created.body.tags, normalizeTagList([{ tag: TAG }, ' TEST-ZARI-209-WELCOME ']));
  assert.deepEqual(created.body.tags, [TAG], 'duplicates and object form are normalised away');
});
