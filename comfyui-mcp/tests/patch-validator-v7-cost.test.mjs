import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

// Test the exact function from the patched vendor file, not a parallel rewrite.
const source = readFileSync(
  process.env.COMFY_MCP_VALIDATOR_FILE ||
  '/usr/local/lib/node_modules/comfyui-mcp/dist/services/workflow-validator.js',
  'utf8',
);
const begin = source.indexOf('function checkComboValues(');
const end = source.indexOf('\n}\n', begin);
assert.ok(begin >= 0 && end > begin, 'checkComboValues must exist');
const checkComboValues = runInNewContext(source.slice(begin, end + 2) + '\ncheckComboValues;', {});
const manyImages = Array.from({length: 187}, (_, i) => 'other-' + i + '.png');

test('missing LoadImage filename returns a bounded staging hint, not image inventory', () => {
  const issues = [];
  checkComboValues('1', 'LoadImage', {image: 'unknown-kuna.png'}, issues,
    {LoadImage: {input: {required: {image: [manyImages]}}}});
  assert.equal(issues.length, 1);
  assert.equal(issues[0].kind, 'value_not_in_list');
  assert.equal(issues[0].severity, 'error');
  assert.match(issues[0].message, /get_output_image_ref/);
  assert.match(issues[0].message, /stage_output_image_reference/);
  assert.doesNotMatch(issues[0].message, /other-0\.png/);
  assert.ok(issues[0].message.length < 400);
});

test('valid LoadImage value is unchanged', () => {
  const issues = [];
  checkComboValues('1', 'LoadImage', {image: 'other-10.png'}, issues,
    {LoadImage: {input: {required: {image: [manyImages]}}}});
  assert.equal(issues.length, 0);
});

test('non-media combo still provides legacy option hints', () => {
  const issues = [];
  checkComboValues('2', 'KSampler', {sampler_name: 'not-a-sampler'}, issues,
    {KSampler: {input: {required: {sampler_name: [['euler', 'heun']]}}}});
  assert.equal(issues.length, 1);
  assert.match(issues[0].message, /Valid options:/);
  assert.match(issues[0].message, /euler/);
});

test('subfolder media reference warning is preserved', () => {
  const issues = [];
  checkComboValues('3', 'LoadImage', {image: 'brand/example.png'}, issues,
    {LoadImage: {input: {required: {image: [manyImages]}}}});
  assert.equal(issues.length, 1);
  assert.equal(issues[0].kind, 'subfolder_reference');
  assert.equal(issues[0].severity, 'warning');
});
