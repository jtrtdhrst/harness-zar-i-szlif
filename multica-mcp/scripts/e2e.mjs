const url = (process.env.MCP_URL || 'https://mcp-multifca.zariszlif.pl/mcp').replace(/\/$/, '');
const apiUrl = (process.env.MULTICA_API_URL || 'https://multica.zariszlif.pl').replace(/\/$/, '');
const token = process.env.MULTICA_TOKEN;
const workspaceId = process.env.TEST_WORKSPACE_ID;
if (!token || !workspaceId) throw new Error('MULTICA_TOKEN and TEST_WORKSPACE_ID are required; no stored credential fallback is used.');

let requestId = 0;
async function rpc(method, params = {}) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json', accept: 'application/json, text/event-stream' },
    body: JSON.stringify({ jsonrpc: '2.0', id: ++requestId, method, params }),
  });
  if (!response.ok) throw new Error(`MCP HTTP ${response.status} for ${method}`);
  return response.json();
}
async function callTool(name, args) {
  const response = await rpc('tools/call', { name, arguments: args });
  if (response.error) throw new Error(`${name}: ${response.error.message}`);
  if (response.result?.isError) throw new Error(`${name}: ${response.result.content?.[0]?.text || 'tool error'}`);
  return response.result?.structuredContent;
}
function entityId(value) {
  return value?.id || value?.uuid || value?.project?.id || value?.project?.uuid || value?.issue?.id || value?.issue?.uuid;
}

let projectId;
let issueId;
try {
  const initialized = await rpc('initialize', { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'multica-mcp-e2e', version: '0.1.0' } });
  if (!initialized.result?.serverInfo?.name) throw new Error('initialize response missing serverInfo');
  const listed = await rpc('tools/list');
  const names = new Set(listed.result?.tools?.map((tool) => tool.name));
  for (const name of ['multica__project__create', 'multica__project__delete', 'multica__issue__create', 'multica__issue__get']) {
    if (!names.has(name)) throw new Error(`tools/list omitted ${name}`);
  }

  const suffix = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14);
  const project = await callTool('multica__project__create', {
    workspace_id: workspaceId,
    title: `MCP Adapter E2E ${suffix}`,
    description: 'Disposable project created and removed by the Multica MCP E2E check.',
  });
  projectId = entityId(project);
  if (!projectId) throw new Error('project.create returned no project id');

  const title = `MCP adapter round-trip ${suffix}`;
  const created = await callTool('multica__issue__create', {
    workspace_id: workspaceId,
    title,
    project: projectId,
    description: 'Disposable MCP adapter write/readback fixture.',
  });
  issueId = entityId(created);
  if (!issueId) throw new Error('issue.create returned no issue id');

  const readback = await callTool('multica__issue__get', { workspace_id: workspaceId, id: issueId });
  const actualTitle = readback?.title || readback?.issue?.title;
  if (actualTitle !== title) throw new Error(`issue readback mismatch: expected ${title}`);

  // List operations emit a top-level CLI array; MCP requires `structuredContent`
  // to be a JSON object, so the adapter must return an `items` envelope.
  for (const name of ['multica__agent__list', 'multica__workspace__mcp__list']) {
    const listed = await callTool(name, { workspace_id: workspaceId, output: 'json' });
    if (!listed || typeof listed !== 'object' || Array.isArray(listed) || !Array.isArray(listed.items)) {
      throw new Error(`${name} structuredContent is not an items record`);
    }
  }

  await callTool('multica__project__delete', { workspace_id: workspaceId, id: projectId, confirm: true });
  projectId = undefined;
  console.log(JSON.stringify({ status: 'PASS', transport: 'streamable-http', initialize: true, toolsListed: names.size, writeReadback: true, disposableProjectCleaned: true, issueId }));
} finally {
  // The MCP intentionally exposes no issue.delete; project deletion does not
  // cascade, so remove the disposable issue through the native API.
  if (issueId) {
    try {
      const response = await fetch(`${apiUrl}/api/issues/${issueId}?workspace_id=${encodeURIComponent(workspaceId)}`, {
        method: 'DELETE',
        headers: { authorization: `Bearer ${token}` },
      });
      if (!response.ok && response.status !== 404) throw new Error(`HTTP ${response.status}`);
    } catch {
      console.error('E2E issue cleanup failed; inspect and remove only the newly-created disposable issue.');
    }
  }
  if (projectId) {
    try { await callTool('multica__project__delete', { workspace_id: workspaceId, id: projectId, confirm: true }); }
    catch { console.error('E2E cleanup failed; inspect and remove only the newly-created disposable project.'); }
  }
}
