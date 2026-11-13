import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

export const ROOT_COMMANDS = [
  'agent', 'autopilot', 'chat', 'issue', 'label', 'project', 'property',
  'repo', 'skill', 'squad', 'view', 'workflow', 'workspace', 'daemon',
  'runtime', 'attachment', 'auth', 'config', 'login', 'setup', 'update',
  'user', 'version',
];

const LOCAL_ONLY = /^(daemon\.|auth\.|config\.|login$|setup\.|update$|version$|runtime\.profile\.|workspace\.switch$)/;
const HOST_FILES = /^(attachment\.|agent\.avatar$)/;
const OMIT_FILE_FLAGS = /(?:^|[-_])(?:file|stdin)(?:$|[-_])/i;

export function isHostLocalFlag(path, name) {
  return OMIT_FILE_FLAGS.test(name)
    || name === 'attachment'
    || name === 'avatar'
    || (name === 'path' && path.startsWith('runtime.profile.'));
}

function help(cli, path) {
  const run = spawnSync(cli, [...path, '--help'], {
    encoding: 'utf8',
    timeout: 5000,
    maxBuffer: 1024 * 1024,
    env: { PATH: process.env.PATH || '/usr/local/bin:/usr/bin:/bin', HOME: '/tmp/multica-catalog' },
  });
  return { text: `${run.stdout || ''}\n${run.stderr || ''}`, code: run.status ?? 1 };
}

export function parseSubcommands(text) {
  const section = text.match(/(?:^|\n)COMMANDS\s*\n([\s\S]*?)(?:\n\s*\n|\nFLAGS\b|$)/);
  if (!section) return [];
  return [...section[1].matchAll(/^\s{2,}([a-z][a-z0-9-]*):\s*(.*)$/gm)]
    .map(([, name]) => name);
}

function jsonType(flagType) {
  if (/^(?:bool|boolean)$/.test(flagType)) return { type: 'boolean' };
  if (/^(?:int|int8|int16|int32|int64|uint|uint8|uint16|uint32|uint64|count)$/.test(flagType)) return { type: 'integer' };
  if (/^(?:float32|float64|number)$/.test(flagType)) return { type: 'number' };
  if (flagType === 'duration') return { type: 'string' };
  if (/^(?:stringArray|stringSlice|strings|intSlice)$/.test(flagType)) {
    return { type: 'array', items: /int/i.test(flagType) ? { type: 'integer' } : { type: 'string' } };
  }
  if (/^(?:stringToString|mapStringString)$/.test(flagType)) return { type: 'object', additionalProperties: { type: 'string' } };
  return { type: 'string' };
}

export function parseFlags(text) {
  const start = text.search(/(?:^|\n)FLAGS\s*\n/);
  if (start < 0) return [];
  const tail = text.slice(start).replace(/^.*?FLAGS\s*\n/, '');
  const block = tail.split(/\n(?:INHERITED FLAGS|LEARN MORE)\b/)[0];
  const flags = [];
  for (const line of block.split('\n')) {
    const match = line.match(/^\s{2,}(?:-[a-z],\s*)?--([a-z][a-z0-9-]*)(?:\s+([A-Za-z][A-Za-z0-9]*))?\s{2,}(.*)$/i);
    if (!match || match[1] === 'help') continue;
    const [, name, rawType = 'bool', description] = match;
    flags.push({
      name,
      rawType,
      schema: jsonType(rawType),
      description: description.trim(),
      required: /\(required\)\s*$/i.test(description),
    });
  }
  return flags;
}

export function parsePositionals(text, path) {
  const usageSection = text.match(/(?:^|\n)USAGE[ \t]*\n([\s\S]*?)(?:\n\s*\n|$)/)?.[1];
  const usage = usageSection?.match(/^\s+multica\s+(.+)$/m)?.[1]?.trim();
  if (!usage) return [];
  const tokens = usage.split(/\s+/).slice(path.split('.').length);
  const positionals = [];
  for (const token of tokens) {
    if (token === '[flags]' || token === '[flags...]') break;
    // Cobra renders value alternatives as one token, e.g. `<limit|none>`; use the
    // first alternative as the input property name so the positional is not dropped.
    const required = /^<([a-z][a-z0-9|_-]*)>$/i.exec(token);
    const optional = /^\[([a-z][a-z0-9|_-]*)\]$/i.exec(token);
    const repeated = /^<([a-z][a-z0-9_-]*)\.\.\.>$/i.exec(token);
    const match = required || optional || repeated;
    if (!match) continue;
    positionals.push({ name: match[1].split('|')[0], required: Boolean(required), repeated: Boolean(repeated) });
  }
  return positionals;
}

export function isLocalOnly(path) {
  // workspace.switch persists a default workspace in the profile's shared HOME,
  // so it would silently retarget other callers of the same MCP container.
  return LOCAL_ONLY.test(path);
}

function classification(path, flags) {
  if (isLocalOnly(path)) {
    return { status: 'ARCHITECTURALLY_INCOMPATIBLE', reason: 'This CLI command manages local authentication, configuration, daemon state, or runtime profile files; a remote MCP container must not impersonate or control the host CLI runtime.' };
  }
  if (HOST_FILES.test(path)) {
    return { status: 'BLOCKED', reason: 'The CLI command reads or writes a path on the CLI host, which is not the MCP caller’s filesystem.' };
  }
  const requiredLocalFile = flags.find((flag) => flag.required && isHostLocalFlag(path, flag.name));
  if (requiredLocalFile) {
    return { status: 'BLOCKED', reason: `Required CLI flag --${requiredLocalFile.name} is a host-local file/path input; no caller-byte transport is provided.` };
  }
  return { status: 'PASS_NATIVE', reason: 'Invoked through the pinned Multica v0.8.1 CLI using the caller’s bearer token; Multica remains the authorization authority.' };
}

export function buildCatalog(cli = process.env.MULTICA_CLI || '/usr/local/bin/multica') {
  const versionRun = spawnSync(cli, ['--version'], {
    encoding: 'utf8', timeout: 5000, maxBuffer: 64 * 1024,
    env: { PATH: process.env.PATH || '/usr/local/bin:/usr/bin:/bin', HOME: '/tmp/multica-catalog' },
  });
  const versionText = `${versionRun.stdout || ''}${versionRun.stderr || ''}`.trim();
  if (versionRun.status !== 0 || !versionText.includes('0.8.1') || !versionText.includes('b1ea927de')) {
    throw new Error('Pinned Multica CLI mismatch; expected v0.8.1 commit b1ea927de.');
  }

  const paths = [];
  const visit = (parts, depth = 0) => {
    if (depth > 5) return;
    const { text, code } = help(cli, parts);
    if (code !== 0 && !text.includes('COMMANDS')) return;
    const children = parseSubcommands(text);
    if (children.length) {
      for (const child of children) visit([...parts, child], depth + 1);
    } else {
      paths.push(parts.join('.'));
    }
  };
  for (const root of ROOT_COMMANDS) visit([root]);

  const entries = [...new Set(paths)].sort().map((path) => {
    const parts = path.split('.');
    const { text } = help(cli, parts);
    const flags = parseFlags(text);
    const positionals = parsePositionals(text, path);
    const { status, reason } = classification(path, flags);
    const exposed = flags.filter((flag) => flag.name !== 'help' && !isHostLocalFlag(path, flag.name));
    const properties = Object.fromEntries(exposed.map((flag) => [flag.name, {
      ...flag.schema,
      description: flag.description,
    }]));
    for (const positional of positionals) {
      properties[positional.name] = positional.repeated
        ? { type: 'array', items: { type: 'string' }, description: `Positional argument for ${path}.` }
        : { type: 'string', description: `Positional argument for ${path}.` };
    }
    properties.workspace_id = {
      type: 'string',
      description: 'Optional Multica workspace UUID. Forwarded as native CLI context; Multica validates membership and role.',
    };
    if (/\.(?:delete|remove|stop|restart|restore|archive|kill|reset|revoke|unset-path)$/.test(path)) {
      properties.confirm = { type: 'boolean', description: 'Must be true for this destructive operation.' };
    }
    const required = [
      ...exposed.filter((flag) => flag.required).map((flag) => flag.name),
      ...positionals.filter((positional) => positional.required).map((positional) => positional.name),
    ];
    return {
      path,
      name: `multica__${path.replaceAll('.', '__')}`,
      status,
      reason,
      destructive: Object.hasOwn(properties, 'confirm'),
      nativeFlags: flags.map(({ name, rawType, required }) => ({ name, type: rawType, required })),
      positionals,
      omittedFlags: flags.filter((flag) => isHostLocalFlag(path, flag.name)).map(({ name, description }) => ({ name, reason: 'host-local file/path/stdin is not accepted over MCP', description })),
      inputSchema: { type: 'object', properties, required, additionalProperties: false },
    };
  });
  return {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    multica: { version: '0.8.1', commit: 'b1ea927def6490c43bedff537b6f4ed9a47fa828', cliVersion: versionText },
    adapter: { version: '0.1.0', transports: ['stdio', 'streamable-http'], tokenFlow: 'per-request bearer PAT or task-scoped mat_ token; no credential fallback' },
    counts: {
      total: entries.length,
      passNative: entries.filter((x) => x.status === 'PASS_NATIVE').length,
      blocked: entries.filter((x) => x.status === 'BLOCKED').length,
      incompatible: entries.filter((x) => x.status === 'ARCHITECTURALLY_INCOMPATIBLE').length,
    },
    operations: entries,
  };
}

export function loadPaperclipBaseline(path = new URL('./docs/paperclip-tool-baseline.json', import.meta.url)) {
  const value = JSON.parse(readFileSync(path, 'utf8'));
  const names = [...value.tools, ...(value.additionalTools || [])];
  if (names.length !== 200 || new Set(names).size !== 200) throw new Error(`Expected 200 unique read-only Paperclip baseline tools, got ${names.length}.`);
  return {
    ...value,
    tools: names.map((name) => ({ name, status: value.directParity, reason: value.reason })),
  };
}
