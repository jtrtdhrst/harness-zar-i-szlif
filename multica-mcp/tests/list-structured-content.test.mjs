import test from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

// Regression coverage for the MCP output-schema boundary: `structuredContent` must
// always be a JSON object (record). List operations emit a top-level CLI array and
// used to be forwarded verbatim, which clients reject with
// 'expected record, path ["structuredContent"], received array'.

const NL = String.fromCharCode(10);
const WS = '28378cc8-2c3a-4f8e-af1c-63e308407b17';
const TOKEN = 'mat_listcontent0123456789ab';

const dir = mkdtempSync(join(tmpdir(), 'multica-mcp-list-'));
const fakeCli = join(dir, 'fake-multica.mjs');

const helpText = {
  'agent': ['COMMANDS', '  list: list agents', '  get: get one agent', '', 'FLAGS', ''].join(NL),
  'agent/list': ['FLAGS', '  --output string     Output format', ''].join(NL),
  'agent/get': ['USAGE', '  multica agent get <id> [flags]', '', 'FLAGS', '  --output string     Output format', ''].join(NL),
  'workspace': ['COMMANDS', '  mcp: registered MCP servers', '', 'FLAGS', ''].join(NL),
  'workspace/mcp': ['COMMANDS', '  list: list registered MCP servers', '', 'FLAGS', ''].join(NL),
  'workspace/mcp/list': ['FLAGS', '  --output string     Output format', ''].join(NL),
};

const source = [
  '#!/usr/bin/env node',
  'const args = process.argv.slice(2);',
  "if (args[0] === '--version') { console.log('multica 0.8.1 (commit b1ea927de, built test)'); process.exit(0); }",
  "const wantHelp = args.at(-1) === '--help';",
  "const path = args.filter((x) => x !== '--server-url' && x !== '--workspace-id' && x !== 'https://multica.zariszlif.pl' && !/^[0-9a-f-]{36}$/i.test(x) && !x.startsWith('--'));",
  `const HELP = ${JSON.stringify(helpText)};`,
  `const NL = ${JSON.stringify(NL)};`,
  "const route = path.join('/');",
  'if (wantHelp) { console.log(HELP[route] || (NL + "FLAGS" + NL)); process.exit(0); }',
  "if (path[0] === 'agent' && path[1] === 'list') { console.log(JSON.stringify([{ id: 'agent-1', name: 'engineer' }, { id: 'agent-2', name: 'cto' }])); process.exit(0); }",
  "if (path[0] === 'workspace' && path[1] === 'mcp' && path[2] === 'list') { console.log(JSON.stringify([{ id: 'mcp-1', name: 'hindsight-ceo', transport: 'http' }])); process.exit(0); }",
  "if (path[0] === 'agent' && path[1] === 'get') { console.log(JSON.stringify({ id: 'agent-1', name: 'engineer' })); process.exit(0); }",
  'console.log(JSON.stringify({ argv: args }));',
].join(NL);

writeFileSync(fakeCli, source);
chmodSync(fakeCli, 0o755);
process.env.MULTICA_CLI = fakeCli;
// Each test process owns a private CLI HOME; never reuse the global /tmp/multica-mcp-home.
process.env.MULTICA_MCP_HOME = join(dir, 'home');

const { startHttpServer, toStructuredContent } = await import('../server.mjs');

const isRecord = (value) => Boolean(value) && typeof value === 'object' && !Array.isArray(value);

test('toStructuredContent always yields a record', () => {
  assert.deepEqual(toStructuredContent([]), { items: [] });
  assert.deepEqual(toStructuredContent([{ id: 'a' }]), { items: [{ id: 'a' }] });
  assert.deepEqual(toStructuredContent({ id: 'a' }), { id: 'a' });
  assert.deepEqual(toStructuredContent(null), { value: null });
  assert.deepEqual(toStructuredContent('text'), { value: 'text' });
  assert.deepEqual(toStructuredContent(7), { value: 7 });
  for (const value of [[], [1], {}, null, 'x', 3, true]) assert(isRecord(toStructuredContent(value)));
});

test('list tools return record structuredContent over MCP', async (t) => {
  const server = startHttpServer(0);
  await new Promise((resolve) => server.once('listening', resolve));
  t.after(() => new Promise((resolve) => {
    server.closeAllConnections();
    server.close(resolve);
  }));
  const base = `http://127.0.0.1:${server.address().port}`;
  const headers = { authorization: `Bearer ${TOKEN}`, 'content-type': 'application/json' };
  const rpc = (method, params) => fetch(`${base}/mcp`, {
    method: 'POST', headers, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
  }).then((response) => response.json());

  const listed = await rpc('tools/list');
  const tools = new Map(listed.result.tools.map((tool) => [tool.name, tool]));
  for (const name of ['multica__agent__list', 'multica__workspace__mcp__list', 'multica__agent__get']) {
    assert(tools.has(name), `tools/list omitted ${name}`);
    assert.deepEqual(Object.keys(tools.get(name)).sort(), ['description', 'inputSchema', 'name']);
  }

  const agentList = await rpc('tools/call', { name: 'multica__agent__list', arguments: { output: 'json', workspace_id: WS } });
  assert.equal(agentList.result.isError, false, agentList.result.content?.[0]?.text ?? 'CLI failed without diagnostic');
  assert.equal(Array.isArray(agentList.result.structuredContent), false, 'structuredContent must not be a top-level array');
  assert(isRecord(agentList.result.structuredContent));
  assert.deepEqual(agentList.result.structuredContent, { items: [{ id: 'agent-1', name: 'engineer' }, { id: 'agent-2', name: 'cto' }] });
  assert.deepEqual(JSON.parse(agentList.result.content[0].text), [{ id: 'agent-1', name: 'engineer' }, { id: 'agent-2', name: 'cto' }]);

  const mcpList = await rpc('tools/call', { name: 'multica__workspace__mcp__list', arguments: { output: 'json', workspace_id: WS } });
  assert.equal(mcpList.result.isError, false);
  assert.equal(Array.isArray(mcpList.result.structuredContent), false, 'structuredContent must not be a top-level array');
  assert.deepEqual(mcpList.result.structuredContent, { items: [{ id: 'mcp-1', name: 'hindsight-ceo', transport: 'http' }] });

  const agentGet = await rpc('tools/call', { name: 'multica__agent__get', arguments: { id: 'agent-1' } });
  assert.equal(agentGet.result.isError, false);
  assert.deepEqual(agentGet.result.structuredContent, { id: 'agent-1', name: 'engineer' }, 'object results stay unwrapped');
});

test.after(() => rmSync(dir, { recursive: true, force: true }));
