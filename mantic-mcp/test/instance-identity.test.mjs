/**
 * DOD-05 — a read-only tool must report the instance base host and the
 * credential identity, and must never echo a token, header or secret.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import { toolHandlers, toolDefinitions } from '../build/tools/instance.js';
import { axiosError, mockClient } from './helpers.mjs';

const IDENTITY_KEY = 'get_instance_identity';

test('the identity tool is read-only: no arguments, no writes', () => {
  const definition = toolDefinitions.find((item) => item.name === IDENTITY_KEY);
  assert.ok(definition, 'get_instance_identity must be advertised');
  assert.deepEqual(Object.keys(definition.inputSchema.properties ?? {}), []);
});

test('identity reports base host and credential identity without leaking secrets', async () => {
  const client = mockClient({
    routes: {
      'v1:GET:/users/self': {
        status: 200,
        data: { user: { id: 3, username: 'lifecycle-ops', email: 'ops@example.invalid', role: { name: 'admin' } } },
      },
      'v2:GET:': { status: 200, data: { '@context': '/api/v2/contexts/Entrypoint' } },
    },
  });

  const result = await toolHandlers[IDENTITY_KEY](client, {});
  const text = result.content[0].text;
  const payload = JSON.parse(text.slice(text.indexOf('{')));

  assert.equal(payload.baseHost, 'mautic.example.pl');
  assert.equal(payload.baseScheme, 'https');
  assert.equal(payload.credential.username, 'lifecycle-ops');
  assert.equal(payload.credential.role, 'admin');
  assert.equal(payload.apiV2.available, true);
  assert.equal(payload.mauticVersion, null, 'no version may be invented');

  assert.doesNotMatch(text, new RegExp(client.accessToken));
  assert.doesNotMatch(text, new RegExp(client.clientSecret));
  assert.doesNotMatch(text, /Bearer/i);
  assert.doesNotMatch(text, /authorization/i);
  assert.doesNotMatch(text, /"headers"/i);

  // Read-only: the tool may only issue GETs.
  assert.deepEqual([...new Set(client.calls.map((call) => call.method))], ['GET']);
});

test('identity stays useful when the credential cannot read /users/self', async () => {
  const client = mockClient({
    routes: {
      'v1:GET:/users/self': () => { throw axiosError(401, {}); },
      'v2:GET:': () => { throw axiosError(404, {}); },
    },
  });

  const result = await toolHandlers[IDENTITY_KEY](client, {});
  const text = result.content[0].text;
  const payload = JSON.parse(text.slice(text.indexOf('{')));

  assert.equal(payload.baseHost, 'mautic.example.pl');
  assert.equal(payload.credential.available, false);
  assert.equal(payload.credential.status, 401);
  assert.equal(payload.apiV2.available, false);
  assert.equal(payload.apiV2.status, 404);
  assert.doesNotMatch(text, new RegExp(client.accessToken));
});
