import test from 'node:test';
import assert from 'node:assert/strict';
import { isHostLocalFlag, parseFlags, parsePositionals, parseSubcommands } from '../catalog.mjs';

test('reads Cobra command and flag metadata without losing repeated values', () => {
  assert.deepEqual(parseSubcommands('COMMANDS\n  create: Create one\n  get: Read one\n\nFLAGS\n'), ['create', 'get']);
  const flags = parseFlags(`FLAGS\n  --title string       Issue title (required)\n  --labels strings     Repeatable labels\n  --dry-run            Do not write\n  -h, --help           help for create\n\nINHERITED FLAGS\n`);
  assert.deepEqual(flags.map((flag) => [flag.name, flag.schema.type, flag.required]), [
    ['title', 'string', true],
    ['labels', 'array', false],
    ['dry-run', 'boolean', false],
  ]);
});

test('distinguishes host-local files from native logical paths and attachment IDs', () => {
  assert.equal(isHostLocalFlag('skill.files.upsert', 'path'), false);
  assert.equal(isHostLocalFlag('issue.create', 'attachment-id'), false);
  assert.equal(isHostLocalFlag('issue.create', 'attachment'), true);
  assert.equal(isHostLocalFlag('skill.files.upsert', 'content-file'), true);
});

test('maps required positional arguments separately from flags', () => {
  assert.deepEqual(parsePositionals('Example: multica issue status <id> cancelled --duplicate-of <original>\n\nUSAGE\n  multica issue status <id> <status> [flags]\n', 'issue.status'), [
    { name: 'id', required: true, repeated: false },
    { name: 'status', required: true, repeated: false },
  ]);
});

test('keeps positional arguments that list value alternatives', () => {
  assert.deepEqual(parsePositionals('USAGE\n  multica runtime concurrency <runtime-id> <limit|none> [flags]\n', 'runtime.concurrency'), [
    { name: 'runtime-id', required: true, repeated: false },
    { name: 'limit', required: true, repeated: false },
  ]);
});
