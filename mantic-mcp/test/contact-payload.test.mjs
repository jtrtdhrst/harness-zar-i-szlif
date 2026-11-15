/**
 * DOD-02 — no tool may advertise an input it silently ignores. `customFields`
 * is flattened into the provider payload (no nested object is ever sent), and a
 * tag carried through it is read back instead of assumed.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import { toolHandlers as contactHandlers, toolDefinitions as contactDefinitions } from '../build/tools/contacts.js';
import { mockClient } from './helpers.mjs';

const TAG = 'TEST-ZARI-209-WELCOME';

test('create_contact flattens customFields into the top-level provider body', async () => {
  const client = mockClient({
    routes: {
      'v1:POST:/contacts/new': {
        status: 200,
        data: { contact: { id: 7, email: 'fixture@example.invalid' } },
      },
      'v1:GET:/contacts/7': { status: 200, data: { contact: { id: 7, tags: [TAG] } } },
    },
  });

  await contactHandlers.create_contact(client, {
    email: 'fixture@example.invalid',
    firstName: 'Fixture',
    customFields: { tags: [TAG], company_size: '3' },
  });

  const [created] = client.calls.filter((call) => call.method === 'POST');
  assert.equal(created.path, '/contacts/new');
  assert.equal('customFields' in created.body, false, 'the nested customFields object must not be sent');
  assert.deepEqual(created.body.tags, [TAG]);
  assert.equal(created.body.company_size, '3', 'custom field aliases belong at the top level');
  assert.equal(created.body.firstName, 'Fixture');
});

test('create_contact verifies tags that came in through customFields', async () => {
  const client = mockClient({
    routes: {
      'v1:POST:/contacts/new': { status: 200, data: { contact: { id: 7 } } },
      // The provider dropped the tag: the create must not be reported as clean success.
      'v1:GET:/contacts/7': { status: 200, data: { contact: { id: 7, tags: [] } } },
    },
  });

  await assert.rejects(
    () => contactHandlers.create_contact(client, { email: 'a@example.invalid', customFields: { tags: [TAG] } }),
    /not confirmed/,
  );
});

test('update_contact flattens customFields and confirms tags by read-back', async () => {
  const client = mockClient({
    routes: {
      'v1:PATCH:/contacts/2/edit': { status: 200, data: { contact: { id: 2 } } },
      'v1:GET:/contacts/2': { status: 200, data: { contact: { id: 2, tags: [TAG] } } },
    },
  });

  const result = await contactHandlers.update_contact(client, { id: 2, customFields: { tags: [TAG] } });

  const [patched] = client.calls.filter((call) => call.method === 'PATCH');
  assert.equal(patched.path, '/contacts/2/edit');
  assert.equal('customFields' in patched.body, false);
  assert.deepEqual(patched.body.tags, [TAG]);
  assert.match(result.content[0].text, /Confirmed tags \(read back\)/);
});

test('update_contact with a stale read reports an explicit error, not success', async () => {
  const client = mockClient({
    routes: {
      'v1:PATCH:/contacts/2/edit': { status: 200, data: { contact: { id: 2 } } },
      'v1:GET:/contacts/2': { status: 200, data: { contact: { id: 2, tags: [] } } },
    },
  });

  await assert.rejects(
    () => contactHandlers.update_contact(client, { id: 2, customFields: { tags: [TAG] } }),
    (error) => {
      assert.match(error.message, /not confirmed/);
      assert.doesNotMatch(error.message, /updated successfully/i);
      return true;
    },
  );
});

test('every tool that exposes customFields has a translation path (no other tool carries it)', () => {
  const carriers = contactDefinitions
    .filter((definition) => 'customFields' in (definition.inputSchema.properties ?? {}))
    .map((definition) => definition.name);

  assert.deepEqual(carriers.sort(), ['create_contact', 'update_contact']);
  for (const definition of contactDefinitions.filter((d) => carriers.includes(d.name))) {
    assert.match(
      definition.inputSchema.properties.customFields.description,
      /flattened to a top-level contact property/,
      `${definition.name}.customFields must document the flattening`,
    );
  }
});
