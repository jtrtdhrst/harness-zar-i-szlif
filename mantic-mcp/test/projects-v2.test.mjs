/**
 * DOD-04 — a bare provider 401 must never surface as success or as an
 * unrelated failure: `list_projects` (and its v2 siblings) must name the API
 * v2 unavailability explicitly.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import { toolHandlers } from '../build/tools/projects.js';
import { McpError } from '../build/errors.js';
import { axiosError, mockClient } from './helpers.mjs';

test('list_projects returns the real project list on 200', async () => {
  const client = mockClient({
    routes: {
      'v2:GET:/projects': {
        status: 200,
        data: { 'hydra:member': [{ id: 1, name: 'Project One' }], 'hydra:totalItems': 1 },
      },
    },
  });

  const result = await toolHandlers.list_projects(client, {});
  assert.match(result.content[0].text, /Found 1 projects/);
  assert.match(result.content[0].text, /Project One/);
});

test('list_projects turns a provider 401 into a typed v2-unavailability error', async () => {
  const client = mockClient({
    routes: { 'v2:GET:/projects': () => { throw axiosError(401, { errors: [{ message: 'Unauthorized' }] }); } },
  });

  await assert.rejects(
    () => toolHandlers.list_projects(client, {}),
    (error) => {
      assert.ok(error instanceof McpError, 'must be a typed MCP error');
      assert.match(error.message, /Mautic API v2/);
      assert.match(error.message, /HTTP 401/);
      assert.doesNotMatch(error.message, /Found \d+ projects/);
      return true;
    },
  );
});

test('list_projects turns a 404 into a typed v2-not-exposed error', async () => {
  const client = mockClient({
    routes: { 'v2:GET:/projects': () => { throw axiosError(404, {}); } },
  });

  await assert.rejects(() => toolHandlers.list_projects(client, {}), /may not expose API Platform v2/);
});

test('every v2 project sibling maps a 401 the same way', async () => {
  const cases = [
    ['get_project', { id: 5 }, 'v2:GET:/projects/5'],
    ['create_project', { name: 'x' }, 'v2:POST:/projects'],
    ['update_project', { id: 5, name: 'x' }, 'v2:PUT:/projects/5'],
    ['patch_project', { id: 5, name: 'x' }, 'v2:PATCH:/projects/5'],
    ['delete_project', { id: 5 }, 'v2:DELETE:/projects/5'],
  ];

  for (const [tool, args, routeKey] of cases) {
    const client = mockClient({
      routes: { [routeKey]: () => { throw axiosError(401, {}); } },
    });
    await assert.rejects(
      () => toolHandlers[tool](client, args),
      (error) => {
        assert.ok(error instanceof McpError, `${tool} must raise a typed error`);
        assert.match(error.message, /Mautic API v2/, `${tool} must name the v2 surface`);
        assert.match(error.message, /HTTP 401/, `${tool} must keep the provider status`);
        return true;
      },
    );
  }
});
