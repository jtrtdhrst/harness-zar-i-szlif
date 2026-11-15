/**
 * DOD-07 — the tool surface must be recorded and stable (baseline 68, plus the
 * single justified identity tool), and DOD-06 — the campaign descriptions must
 * state the entry sources this server can actually express.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import { allToolDefinitions } from '../build/tools/index.js';

const BASELINE_TOOL_COUNT = 68;

test('tool surface matches the recorded baseline plus the documented addition', () => {
  const names = allToolDefinitions.map((definition) => definition.name);
  const unique = new Set(names);

  assert.equal(unique.size, names.length, 'tool names must stay unique');
  assert.equal(
    names.length,
    BASELINE_TOOL_COUNT + 1,
    `expected ${BASELINE_TOOL_COUNT} baseline tools + get_instance_identity, got ${names.length}`,
  );
  assert.ok(unique.has('get_instance_identity'), 'the DOD-05 identity tool must be registered');
});

test('no tool advertises customFields except the flattened contact tools', () => {
  const carriers = allToolDefinitions
    .filter((definition) => 'customFields' in (definition.inputSchema.properties ?? {}))
    .map((definition) => definition.name)
    .sort();
  assert.deepEqual(carriers, ['create_contact', 'update_contact']);
});

test('campaign creation documents its real entry sources and rejects tag-trigger enrollment', () => {
  const automation = allToolDefinitions.find((item) => item.name === 'create_campaign_with_automation');
  assert.ok(automation);

  assert.match(automation.description, /`segments`/);
  assert.match(automation.description, /`forms`/);
  assert.match(automation.description, /in-campaign event, not an entry source/);
  assert.match(automation.description, /no tag-trigger enrollment/);

  assert.equal(automation.inputSchema.properties.segments.description.includes('entry sources'), true);
  assert.equal(automation.inputSchema.properties.forms.description.includes('entry sources'), true);
  assert.equal(automation.inputSchema.properties.segments.description.includes('trigger campaign'), false);

  const shell = allToolDefinitions.find((item) => item.name === 'create_campaign');
  assert.match(shell.description, /Entry sources are not part of this call/);
});

test('add_contact_tags documents the read-back behaviour', () => {
  const definition = allToolDefinitions.find((item) => item.name === 'add_contact_tags');
  assert.match(definition.description, /merged tag set/);
  assert.match(definition.description, /reads the contact back/);
});
