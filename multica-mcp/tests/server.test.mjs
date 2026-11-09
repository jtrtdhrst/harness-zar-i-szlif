import test from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';

const dir = mkdtempSync(join(tmpdir(), 'multica-mcp-test-'));
const fakeCli = join(dir, 'fake-multica.mjs');
writeFileSync(fakeCli, `#!/usr/bin/env node
const args = process.argv.slice(2);
if (args[0] === '--version') { console.log('multica 0.8.1 (commit b1ea927de, built test)'); process.exit(0); }
const help = args.at(-1) === '--help';
const command = args.filter((x) => x !== '--server-url' && x !== '--workspace-id');
const path = command.filter((x) => !x.startsWith('--') && x !== 'https://multica.zariszlif.pl');
if (help && path.length === 1 && path[0] === 'issue') { console.log('COMMANDS\\n  create: create\\n  get: get\\n\\nFLAGS\\n'); process.exit(0); }
if (help && path.join(' ') === 'issue create') { console.log('FLAGS\\n  --title string       Issue title (required)\\n  --output string      Output format\\n'); process.exit(0); }
if (help && path.join(' ') === 'issue get') { console.log('USAGE\\n  multica issue get <id> [flags]\\n\\nFLAGS\\n  --output string      Output format\\n'); process.exit(0); }
if (help && path.length === 1 && path[0] === 'project') { console.log('COMMANDS\\n  delete: delete\\n\\nFLAGS\\n'); process.exit(0); }
if (help && path.join(' ') === 'project delete') { console.log('USAGE\\n  multica project delete <id> [flags]\\n\\nFLAGS\\n'); process.exit(0); }
if (help && path.length === 1 && path[0] === 'daemon') { console.log('COMMANDS\\n  status: status\\n\\nFLAGS\\n'); process.exit(0); }
if (help && path.join(' ') === 'daemon status') { console.log('FLAGS\\n  --output string     Output format\\n'); process.exit(0); }
console.log(JSON.stringify({ argv: args, tokenPresent: Boolean(process.env.MULTICA_TOKEN), tokenMatches: process.env.MULTICA_TOKEN === 'mat_testtoken123456789abc', token: process.env.MULTICA_TOKEN || '' }));
`);
chmodSync(fakeCli, 0o755);
process.env.MULTICA_CLI = fakeCli;

const { startHttpServer } = await import('../server.mjs');

test('HTTP transport authenticates, exposes the CLI catalog, and forwards caller token/context', async (t) => {
  const server = startHttpServer(0);
  await new Promise((resolve) => server.once('listening', resolve));
  t.after(() => new Promise((resolve) => {
    server.closeAllConnections();
    server.close(resolve);
  }));
  const base = `http://127.0.0.1:${server.address().port}`;
  const unauth = await fetch(`${base}/mcp`, { method: 'POST', body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }) });
  assert.equal(unauth.status, 401);

  const queryHeaders = { 'content-type': 'application/json' };
  const queryAuth = await fetch(`${base}/mcp?key=mat_testtoken123456789abc`, { method: 'POST', headers: queryHeaders, body: JSON.stringify({ jsonrpc: '2.0', id: 20, method: 'tools/list' }) });
  assert.equal(queryAuth.status, 200);
  const queryListing = await queryAuth.json();
  assert(queryListing.result.tools.some((tool) => tool.name === 'multica__issue__create'));
  const queryCall = await fetch(`${base}/mcp?key=mat_testtoken123456789abc`, {
    method: 'POST', headers: queryHeaders,
    body: JSON.stringify({ jsonrpc: '2.0', id: 21, method: 'tools/call', params: {
      name: 'multica__issue__get', arguments: { id: '01a1b749-f45e-73df-b26d-ec906c541ad7' },
    } }),
  }).then((r) => r.json());
  assert.equal(queryCall.result.isError, false);
  assert.equal(queryCall.result.structuredContent.tokenMatches, true);

  const headers = { authorization: 'Bearer mat_testtoken123456789abc', 'content-type': 'application/json' };
  const init = await fetch(`${base}/mcp`, { method: 'POST', headers, body: JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'initialize', params: { protocolVersion: '2025-06-18' } }) }).then((r) => r.json());
  assert.equal(init.result.serverInfo.name, 'multica-control-plane');
  const listing = await fetch(`${base}/mcp`, { method: 'POST', headers, body: JSON.stringify({ jsonrpc: '2.0', id: 3, method: 'tools/list' }) }).then((r) => r.json());
  const names = listing.result.tools.map((tool) => tool.name);
  assert(names.includes('multica__issue__create'));
  assert(!names.includes('multica__daemon__status'));

  const result = await fetch(`${base}/mcp`, {
    method: 'POST', headers,
    body: JSON.stringify({ jsonrpc: '2.0', id: 4, method: 'tools/call', params: {
      name: 'multica__issue__create', arguments: { workspace_id: 'f45460f5-76a8-4c2f-b3eb-5d025a8f8726', title: 'catalog e2e' },
    } }),
  }).then((r) => r.json());
  assert.equal(result.result.isError, false);
  assert.equal(result.result.structuredContent.tokenPresent, true);
  assert.equal(result.result.structuredContent.tokenMatches, true);
  assert(!JSON.stringify(result).includes('mat_testtoken'));
  assert.deepEqual(result.result.structuredContent.argv.slice(0, 4), ['--server-url', 'https://multica.zariszlif.pl', '--workspace-id', 'f45460f5-76a8-4c2f-b3eb-5d025a8f8726']);
  assert(result.result.structuredContent.argv.includes('--output'));

  const invalid = await fetch(`${base}/mcp`, {
    method: 'POST', headers,
    body: JSON.stringify({ jsonrpc: '2.0', id: 5, method: 'tools/call', params: {
      name: 'multica__issue__create', arguments: { title: 'x', unknown: 'bad' },
    } }),
  }).then((r) => r.json());
  assert.equal(invalid.result.isError, true);
  assert.match(invalid.result.content[0].text, /unknown argument/);

  const destructive = await fetch(`${base}/mcp`, {
    method: 'POST', headers,
    body: JSON.stringify({ jsonrpc: '2.0', id: 6, method: 'tools/call', params: {
      name: 'multica__project__delete', arguments: { id: 'fixture' },
    } }),
  }).then((r) => r.json());
  assert.equal(destructive.result.isError, true);
  assert.match(destructive.result.content[0].text, /confirm=true/);
});

test('stdio transport returns MCP initialization and tool call responses', async () => {
  const proc = spawn(process.execPath, [join(import.meta.dirname, '..', 'server.mjs'), 'stdio'], {
    env: { ...process.env, MULTICA_TOKEN: 'mat_stdio_test_token_123456789' },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const lines = [];
  let stderr = '';
  proc.stdout.setEncoding('utf8');
  proc.stderr.setEncoding('utf8');
  proc.stderr.on('data', (chunk) => { stderr += chunk; });
  proc.stdout.on('data', (chunk) => lines.push(...chunk.split('\n').filter(Boolean)));
  proc.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2024-11-05' } })}\n`);
  proc.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'multica__issue__get', arguments: { id: '01a1b749-f45e-73df-b26d-ec906c541ad7' } } })}\n`);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`stdio timeout: ${stderr}`)), 5000);
    const check = () => {
      if (lines.length >= 2) { clearTimeout(timer); resolve(); }
      else setTimeout(check, 10);
    };
    check();
  });
  proc.stdin.end();
  const init = JSON.parse(lines[0]);
  const call = JSON.parse(lines[1]);
  assert.equal(init.result.serverInfo.name, 'multica-control-plane');
  assert.equal(call.result.isError, false);
  assert.equal(call.result.structuredContent.tokenPresent, true);
  assert(call.result.structuredContent.argv.includes('01a1b749-f45e-73df-b26d-ec906c541ad7'));
  await new Promise((resolve) => proc.once('exit', resolve));
});

test.after(() => rmSync(dir, { recursive: true, force: true }));
