import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { buildCatalog, loadPaperclipBaseline } from './catalog.mjs';

const VERSION = '0.1.0';
const API_URL = (process.env.MULTICA_API_URL || 'https://multica.zariszlif.pl').replace(/\/$/, '');
const HTTP_PORT = Number(process.env.PORT || 3000);
const CLI = process.env.MULTICA_CLI || '/usr/local/bin/multica';
const COMMAND_TIMEOUT_MS = 120_000;
const MAX_OUTPUT_BYTES = 2 * 1024 * 1024;
const catalog = buildCatalog(CLI);
const paperclip = loadPaperclipBaseline();
const operations = new Map(catalog.operations.map((entry) => [entry.name, entry]));
const active = new Map();
const home = process.env.MULTICA_MCP_HOME || '/tmp/multica-mcp-home';
mkdirSync(home, { recursive: true, mode: 0o700 });

function safeText(value) {
  return String(value || '')
    .replace(/\b(?:mul|mat|mcn)_[A-Za-z0-9_-]{12,}\b/g, '[REDACTED_TOKEN]')
    .replace(/Bearer\s+[A-Za-z0-9._~-]{12,}/gi, 'Bearer [REDACTED]')
    .replace(/("?(?:password|secret|token|api[_-]?key)"?\s*[:=]\s*"?)[^",\s}]{4,}("?)/gi, '$1[REDACTED]$2')
    .slice(0, MAX_OUTPUT_BYTES);
}

function validationError(entry, args) {
  if (!args || typeof args !== 'object' || Array.isArray(args)) return 'arguments must be an object';
  if (entry.destructive && args.confirm !== true) return 'confirm=true is required for this destructive operation';
  const allowed = new Set(Object.keys(entry.inputSchema.properties));
  for (const key of Object.keys(args)) if (!allowed.has(key)) return `unknown argument: ${key}`;
  for (const key of entry.inputSchema.required) if (args[key] === undefined) return `missing required argument: ${key}`;
  for (const [key, value] of Object.entries(args)) {
    if (key === 'workspace_id' && value !== undefined && !/^[0-9a-f-]{36}$/i.test(value)) return 'workspace_id must be a UUID';
    if (key === 'confirm' && value !== true && entry.destructive) return 'confirm must be true for this destructive operation';
    if (key === 'confirm' && !entry.destructive) return 'confirm is not accepted for this operation';
    if (key === 'workspace_id') continue;
    const schema = entry.inputSchema.properties[key];
    if (schema.type === 'boolean' && typeof value !== 'boolean') return `${key} must be a boolean`;
    if (schema.type === 'string' && typeof value !== 'string') return `${key} must be a string`;
    if (schema.type === 'integer' && !Number.isInteger(value)) return `${key} must be an integer`;
    if (schema.type === 'number' && (typeof value !== 'number' || !Number.isFinite(value))) return `${key} must be a number`;
    if (schema.type === 'array' && (!Array.isArray(value) || value.some((item) => typeof item !== schema.items.type))) return `${key} must be an array of ${schema.items.type}`;
    if (schema.type === 'object' && (!value || typeof value !== 'object' || Array.isArray(value))) return `${key} must be an object`;
  }
  return null;
}

export function cliArguments(entry, input) {
  const args = { ...input };
  const workspace = args.workspace_id;
  delete args.workspace_id;
  delete args.confirm;
  const argv = [];
  if (workspace) argv.push('--workspace-id', workspace);
  argv.push(...entry.path.split('.'));
  for (const positional of entry.positionals) {
    const value = args[positional.name];
    delete args[positional.name];
    if (Array.isArray(value)) argv.push(...value.map(String));
    else if (value !== undefined && value !== null) argv.push(String(value));
  }
  if (entry.inputSchema.properties.output && args.output === undefined) args.output = 'json';
  const flags = new Map(entry.nativeFlags.map((flag) => [flag.name, flag]));
  for (const [name, value] of Object.entries(args)) {
    const meta = flags.get(name);
    if (!meta) throw new Error(`argument --${name} is not in the pinned CLI schema`);
    const flag = `--${name}`;
    if (meta.type === 'bool' || meta.type === 'boolean') {
      if (value) argv.push(flag);
      else argv.push(`${flag}=false`);
    } else if (meta.type === 'stringToString' || meta.type === 'mapStringString') {
      for (const [key, item] of Object.entries(value)) argv.push(flag, `${key}=${item}`);
    } else if (Array.isArray(value)) {
      for (const item of value) argv.push(flag, String(item));
    } else if (value !== undefined && value !== null) {
      argv.push(flag, String(value));
    }
  }
  return argv;
}

function runCli(entry, args, token, requestKey) {
  const argv = ['--server-url', API_URL, ...cliArguments(entry, args)];
  const child = spawn(CLI, argv, {
    shell: false,
    cwd: home,
    env: {
      PATH: process.env.PATH || '/usr/local/bin:/usr/bin:/bin',
      HOME: home,
      MULTICA_TOKEN: token,
      MULTICA_SERVER_URL: API_URL,
      ...(process.env.MULTICA_WORKSPACE_ID ? { MULTICA_WORKSPACE_ID: process.env.MULTICA_WORKSPACE_ID } : {}),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stdout = '';
  let stderr = '';
  let bytes = 0;
  let settled = false;
  let timer;
  const promise = new Promise((resolve) => {
    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      active.delete(requestKey);
      resolve(result);
    };
    const append = (target, chunk) => {
      bytes += chunk.length;
      if (bytes > MAX_OUTPUT_BYTES) {
        child.kill('SIGTERM');
        finish({ ok: false, message: 'CLI output exceeded 2 MiB and was stopped.' });
        return target;
      }
      return target + chunk.toString('utf8');
    };
    child.stdout.on('data', (chunk) => { stdout = append(stdout, chunk); });
    child.stderr.on('data', (chunk) => { stderr = append(stderr, chunk); });
    child.on('error', (error) => finish({ ok: false, message: `Multica CLI could not start: ${error.message}` }));
    child.on('close', (code, signal) => finish({ ok: code === 0, stdout, stderr, code, signal }));
    timer = setTimeout(() => {
      child.kill('SIGTERM');
      finish({ ok: false, message: 'Multica CLI call timed out after 120 seconds.' });
    }, COMMAND_TIMEOUT_MS);
    active.set(requestKey, child);
  });
  return promise;
}

// MCP requires `structuredContent` to be a JSON object (record); a top-level array
// or scalar is rejected by SDK-side schema validation (e.g. "expected record, path
// [\"structuredContent\"], received array"). Several operations emit a top-level JSON
// array (agent.list, workspace.mcp.list, project.list, runtime.list,
// issue.comment.list, issue.timeline), so wrap those in a stable `items` envelope
// and leave object-returning operations untouched.
export function toStructuredContent(value) {
  if (Array.isArray(value)) return { items: value };
  if (value !== null && typeof value === 'object') return value;
  return { value: value ?? null };
}

function toolResult(ok, text, structuredContent) {
  const result = { content: [{ type: 'text', text: safeText(text) }], isError: !ok };
  if (structuredContent !== undefined) result.structuredContent = sanitizeStructured(structuredContent);
  return result;
}

function sanitizeStructured(value) {
  if (Array.isArray(value)) return value.map(sanitizeStructured);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [
      key,
      /(?:password|secret|token|api[_-]?key)$/i.test(key) ? '[REDACTED]' : sanitizeStructured(item),
    ]));
  }
  return typeof value === 'string' ? safeText(value) : value;
}

async function callTool(name, args, token, requestKey) {
  const entry = operations.get(name);
  if (!entry) return toolResult(false, `Unknown Multica operation: ${name}`);
  if (entry.status !== 'PASS_NATIVE') return toolResult(false, `${entry.status}: ${entry.reason}`);
  const validation = validationError(entry, args);
  if (validation) return toolResult(false, validation);
  const result = await runCli(entry, args, token, requestKey);
  if (!result.ok) {
    const message = result.message || safeText(result.stderr || result.stdout || `Multica CLI exited with ${result.code ?? result.signal ?? 'unknown status'}`);
    console.error(`[multica-mcp] operation=${name} failed`);
    return toolResult(false, message);
  }
  const text = [result.stdout, result.stderr].filter(Boolean).join('\n').trim();
  try {
    return toolResult(true, text, toStructuredContent(JSON.parse(result.stdout)));
  } catch {
    return toolResult(true, text || 'Operation completed.');
  }
}

function jsonRpcError(id, code, message) {
  return { jsonrpc: '2.0', id: id ?? null, error: { code, message } };
}

function capabilities() {
  return {
    tools: { listChanged: false },
    resources: { subscribe: false, listChanged: false },
  };
}

function resourceList() {
  return [
    { uri: 'multica://capabilities/v0.8.1.json', name: 'Multica v0.8.1 capability catalog', mimeType: 'application/json', description: 'All discovered CLI commands, flag schemas, and compatibility classifications.' },
    { uri: 'multica://capabilities/paperclip-baseline.json', name: 'Paperclip read-only baseline', mimeType: 'application/json', description: 'The 200-name read-only Paperclip catalog snapshot and explicit target-compatibility findings.' },
  ];
}

async function handleRpc(message, token, transportKey) {
  if (!message || typeof message !== 'object' || Array.isArray(message) || message.jsonrpc !== '2.0' || typeof message.method !== 'string') {
    return jsonRpcError(message?.id, -32600, 'Invalid JSON-RPC request.');
  }
  const id = message.id;
  if (message.method.startsWith('notifications/')) {
    if (message.method === 'notifications/cancelled') {
      const requestId = message.params?.requestId;
      const child = active.get(`${transportKey}:${String(requestId)}`);
      if (child) child.kill('SIGTERM');
    }
    return null;
  }
  if (id === undefined) return null;
  switch (message.method) {
    case 'initialize':
      return { jsonrpc: '2.0', id, result: {
        protocolVersion: ['2025-06-18', '2025-03-26', '2024-11-05'].includes(message.params?.protocolVersion) ? message.params.protocolVersion : '2025-06-18',
        capabilities: capabilities(),
        serverInfo: { name: 'multica-control-plane', version: VERSION },
        instructions: 'Multica operations are executed by the pinned native v0.8.1 CLI with the caller token from the Authorization header or the ?key= query parameter. No admin token or credential fallback is used.',
      } };
    case 'ping':
      return { jsonrpc: '2.0', id, result: {} };
    case 'tools/list':
      return { jsonrpc: '2.0', id, result: {
        tools: catalog.operations.filter((entry) => entry.status === 'PASS_NATIVE').map(({ name, path, reason, destructive, inputSchema }) => ({
          name,
          description: `${path} — ${reason}${destructive ? ' Destructive action: set confirm=true.' : ''}`,
          inputSchema,
        })),
      } };
    case 'tools/call': {
      const name = message.params?.name;
      const args = message.params?.arguments || {};
      const key = `${transportKey}:${String(id)}`;
      const result = await callTool(name, args, token, key);
      return { jsonrpc: '2.0', id, result };
    }
    case 'resources/list':
      return { jsonrpc: '2.0', id, result: { resources: resourceList() } };
    case 'resources/read': {
      const uri = message.params?.uri;
      let value;
      if (uri === 'multica://capabilities/v0.8.1.json') value = catalog;
      else if (uri === 'multica://capabilities/paperclip-baseline.json') value = paperclip;
      else return jsonRpcError(id, -32602, 'Unknown resource URI.');
      return { jsonrpc: '2.0', id, result: { contents: [{ uri, mimeType: 'application/json', text: JSON.stringify(value) }] } };
    }
    case 'prompts/list':
      return { jsonrpc: '2.0', id, result: { prompts: [] } };
    default:
      return jsonRpcError(id, -32601, 'Method not found.');
  }
}

function bearer(req) {
  const match = /^Bearer\s+(\S+)$/i.exec(req.headers.authorization || '');
  if (match) return match[1];
  const url = new URL(req.url || '/', 'http://localhost');
  return url.searchParams.get('key') || url.searchParams.get('token') || null;
}

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 1024 * 1024) throw new Error('request body exceeds 1 MiB');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

export function startHttpServer(port = HTTP_PORT) {
  const server = createServer(async (req, res) => {
    const pathname = new URL(req.url || '/', 'http://localhost').pathname;
    if (req.method === 'GET' && pathname === '/health') {
      res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' });
      res.end(JSON.stringify({ status: 'ok', service: 'multica-control-plane', version: VERSION, multica: catalog.multica, operations: catalog.counts.total }));
      return;
    }
    if (pathname !== '/mcp' || req.method !== 'POST') {
      res.writeHead(404, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ error: 'not_found' }));
      return;
    }
    const token = bearer(req);
    if (!token) {
      res.writeHead(401, { 'content-type': 'application/json', 'www-authenticate': 'Bearer' });
      res.end(JSON.stringify({ error: 'bearer_token_required' }));
      return;
    }
    let message;
    try { message = await readJson(req); }
    catch (error) {
      res.writeHead(400, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ error: error.message === 'request body exceeds 1 MiB' ? error.message : 'invalid_json' }));
      return;
    }
    const transportKey = req.headers['mcp-session-id'] || createHash('sha256').update(token).digest('hex').slice(0, 16);
    try {
      const response = await handleRpc(message, token, transportKey);
      if (response === null) {
        res.writeHead(202, { 'content-length': '0' });
        res.end();
        return;
      }
      res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store', 'mcp-protocol-version': response.result?.protocolVersion || '2025-06-18' });
      res.end(JSON.stringify(response));
    } catch (error) {
      console.error(`[multica-mcp] request failed: ${error.message}`);
      res.writeHead(500, { 'content-type': 'application/json' });
      res.end(JSON.stringify(jsonRpcError(message.id, -32603, 'Internal MCP error.')));
    }
  });
  return server.listen(port, '0.0.0.0');
}

export async function runStdio() {
  const token = process.env.MULTICA_TOKEN;
  if (!token) throw new Error('MULTICA_TOKEN is required; refusing to fall back to a stored profile credential.');
  let buffer = '';
  for await (const chunk of process.stdin) {
    buffer += chunk.toString('utf8');
    let index;
    while ((index = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 1);
      if (!line) continue;
      let message;
      try { message = JSON.parse(line); }
      catch { process.stdout.write(`${JSON.stringify(jsonRpcError(null, -32700, 'Parse error.'))}\n`); continue; }
      const response = await handleRpc(message, token, 'stdio');
      if (response !== null) process.stdout.write(`${JSON.stringify(response)}\n`);
    }
  }
}

if (process.argv[1] && new URL(import.meta.url).pathname === process.argv[1]) {
  const mode = process.argv[2] || 'http';
  if (mode === 'stdio') {
    runStdio().catch((error) => { console.error(error.message); process.exitCode = 1; });
  } else if (mode === 'http') {
    startHttpServer();
    console.log(`[multica-mcp] listening on :${HTTP_PORT}; native CLI ${catalog.multica.version} ${catalog.multica.commit.slice(0, 10)}; operations=${catalog.counts.total}`);
  } else {
    console.error('usage: node server.mjs [http|stdio]');
    process.exitCode = 2;
  }
}
