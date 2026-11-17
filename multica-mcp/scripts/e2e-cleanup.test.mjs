import test from 'node:test';
import assert from 'node:assert/strict';

const testWorkspace = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const names = [
  'multica__project__create', 'multica__project__delete',
  'multica__issue__create', 'multica__issue__get',
  'multica__agent__list', 'multica__workspace__mcp__list',
];

async function scenario(mode) {
  // No network, live API, token or created real fixture: the exact E2E script
  // executes against an in-memory fake server and cannot modify production.
  const beforeEnv = Object.fromEntries(
    ['MCP_URL', 'MULTICA_API_URL', 'MULTICA_TOKEN', 'TEST_WORKSPACE_ID']
      .map(key => [key, process.env[key]])
  );
  const fetchBefore = globalThis.fetch;
  const logBefore = console.log;
  const calls = [];
  const logs = [];
  let deletedIssue = false;
  let deletedProject = false;
  let newTitle;
  const response = (status, body = {}) => ({
    status, ok: status >= 200 && status < 300, json: async () => body,
  });

  try {
    Object.assign(process.env, {
      MCP_URL: 'https://canary.invalid/mcp',
      MULTICA_API_URL: 'https://canary.invalid',
      MULTICA_TOKEN: 'mock-token-NOT-A-REAL-SECRET',
      TEST_WORKSPACE_ID: testWorkspace,
    });
    console.log = line => logs.push(String(line));
    globalThis.fetch = async (url, options = {}) => {
      if (String(url) === 'https://canary.invalid/mcp') {
        const req = JSON.parse(options.body);
        const operation = req.method === 'tools/call' ? req.params.name : req.method;
        calls.push(operation);
        if (req.method === 'initialize')
          return response(200, { result: { serverInfo: { name: 'stub' } } });
        if (req.method === 'tools/list')
          return response(200, { result: { tools: names.map(name => ({ name })) } });
        assert.equal(req.method, 'tools/call');
        if (operation === 'multica__project__create')
          return response(200, { result: { structuredContent: { id: 'new-project' } } });
        if (operation === 'multica__issue__create') {
          newTitle = req.params.arguments.title;
          return response(200, { result: { structuredContent: { id: 'new-issue' } } });
        }
        if (operation === 'multica__issue__get')
          return response(200, { result: { structuredContent: {
            title: mode === 'bad-issue-readback' ? 'wrong' : newTitle,
          } } });
        if (operation === 'multica__agent__list' ||
            operation === 'multica__workspace__mcp__list')
          return response(200, { result: { structuredContent: { items: [] } } });
        if (operation === 'multica__project__delete') {
          if (!deletedIssue || mode === 'project-delete-fails')
            return response(200, { result: {
              isError: true, content: [{ text: 'cannot delete test project' }],
            } });
          deletedProject = true;
          return response(200, { result: { structuredContent: { deleted: true } } });
        }
        throw new Error('Unrecognized mock tool ' + operation);
      }
      if (String(url).startsWith('https://canary.invalid/api/issues/new-issue?')) {
        const method = options.method || 'GET';
        calls.push('HTTP ' + method);
        if (method === 'DELETE') {
          if (mode === 'issue-delete-fails') return response(500);
          deletedIssue = true;
          return response(204);
        }
        return response(mode === 'stale-issue-readback' ? 200 : (deletedIssue ? 404 : 200));
      }
      throw new Error('Unexpected external request (network is forbidden)');
    };

    let error;
    try {
      // The query makes the module evaluate anew for each test scenario.
      await import(new URL('./e2e.mjs?cleanup-test=' + mode, import.meta.url));
    } catch (caught) { error = caught; }
    return { logs, calls, error, deletedIssue, deletedProject };
  } finally {
    globalThis.fetch = fetchBefore;
    console.log = logBefore;
    for (const [key, value] of Object.entries(beforeEnv)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

test('PASS only after issue DELETE + GET 404 + project delete', async () => {
  const r = await scenario('success');
  assert.equal(r.error, undefined);
  assert.equal(r.deletedIssue, true);
  assert.equal(r.deletedProject, true);
  assert.ok(r.calls.indexOf('HTTP DELETE') < r.calls.indexOf('multica__project__delete'));
  assert.ok(r.calls.indexOf('HTTP GET') < r.calls.indexOf('multica__project__delete'));
  assert.equal(r.logs.length, 1);
  const report = JSON.parse(r.logs[0]);
  assert.equal(report.status, 'PASS');
  assert.equal(report.disposableIssueCleaned, true);
  assert.equal(report.disposableProjectCleaned, true);
});

for (const [mode, expected] of [
  ['issue-delete-fails', 'issue cleanup DELETE HTTP 500'],
  ['stale-issue-readback', 'issue cleanup readback expected 404'],
  ['project-delete-fails', 'cannot delete test project'],
  ['bad-issue-readback', 'issue readback mismatch'],
]) {
  test(mode + ' denies PASS and attempts bounded cleanup', async () => {
    const r = await scenario(mode);
    assert.ok(r.error, 'test must fail, not emit success');
    assert.match(String(r.error), new RegExp(expected));
    assert.equal(r.logs.length, 0, 'no PASS on failed assertion or cleanup');
    assert.ok(r.calls.includes('HTTP DELETE'), 'fixture cleanup must still be attempted');
    if (mode === 'issue-delete-fails' || mode === 'stale-issue-readback') {
      assert.equal(r.deletedProject, false, 'never delete project while issue is unverified');
    }
  });
}
