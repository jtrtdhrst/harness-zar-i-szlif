/**
 * DOD-01 / DOD-03 — contact tag writes must use a real Mautic route and must be
 * confirmed by a read-back instead of reporting success blindly.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import { toolHandlers } from '../build/tools/business.js';
import { McpError } from '../build/errors.js';
import { mockClient, sequence } from './helpers.mjs';

const TAG = 'TEST-ZARI-209-WELCOME';

test('add_contact_tags uses the contact edit route with the merged tag set, never the invented /contact/add path', async () => {
  const client = mockClient({
    routes: {
      'v1:GET:/contacts/2': sequence([
        { status: 200, data: { contact: { id: 2, tags: ['existing-tag'] } } },
        { status: 200, data: { contact: { id: 2, tags: ['existing-tag', TAG] } } },
      ]),
      'v1:PATCH:/contacts/2/edit': { status: 200, data: { contact: { id: 2 } } },
    },
  });

  const result = await toolHandlers.add_contact_tags(client, { contactId: 2, tags: [TAG] });

  const patched = client.calls.filter((call) => call.method === 'PATCH');
  assert.equal(patched.length, 1, 'exactly one tag write must be issued');
  assert.equal(patched[0].path, '/contacts/2/edit');
  assert.deepEqual(patched[0].body, { tags: ['existing-tag', TAG] });

  const invented = client.calls.filter((call) => /\/contact\/add$/.test(call.path));
  assert.equal(invented.length, 0, 'the non-existent /contacts/{id}/contact/add route must not be called');

  assert.equal(result.isError, undefined);
  assert.match(result.content[0].text, /Tags confirmed on contact 2/);
  assert.match(result.content[0].text, new RegExp(TAG));
});

test('add_contact_tags fails when the read-back does not contain the requested tag (stale read)', async () => {
  const client = mockClient({
    routes: {
      // Both the pre-read and the verification read report no tags: the write silently did nothing.
      'v1:GET:/contacts/2': { status: 200, data: { contact: { id: 2, tags: [] } } },
      'v1:PATCH:/contacts/2/edit': { status: 200, data: { contact: { id: 2 } } },
    },
  });

  await assert.rejects(
    () => toolHandlers.add_contact_tags(client, { contactId: 2, tags: [TAG] }),
    (error) => {
      assert.ok(error instanceof McpError, 'an explicit MCP error must be raised');
      assert.match(error.message, /not confirmed/);
      assert.match(error.message, new RegExp(TAG));
      assert.doesNotMatch(error.message, /successfully/i);
      return true;
    },
  );
});

test('add_contact_tags rejects an empty tag list instead of writing an empty set', async () => {
  const client = mockClient({ routes: {} });
  await assert.rejects(
    () => toolHandlers.add_contact_tags(client, { contactId: 2, tags: ['  ', ''] }),
    /at least one non-empty tag name/,
  );
  assert.equal(client.calls.length, 0, 'no provider call may happen for invalid input');
});
