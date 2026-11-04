import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
const nativeFetch = globalThis.fetch;

process.env.PAPERCLIP_RUN_ID = 'aaaabbbb-cccc-4ddd-8eee-ffffffff0001';
process.env.PAPERCLIP_AGENT_ID = '11112222-3333-4444-8555-666677778888';
process.env.PAPERCLIP_TASK_ID = '99990000-1111-4222-8333-444455556666';
process.env.OPIK_BASE_URL = 'http://127.0.0.1:32001/mock-opik';
const calls = [];
let failNext = 0;
let failedKind = '';
globalThis.fetch = async (url, init) => {
  calls.push({ url: String(url), body: JSON.parse(init?.body ?? '{}') });
  if (failNext > 0 && String(url).endsWith(failedKind)) {
    failNext -= 1;
    return {ok:false,status:503};
  }
  return {ok:true,status:200};
};
const {default:factory} = await import('./index.mjs?unit-test');
const plugin = await factory();
const event = (info) => plugin.event({event:{type:'message.updated',properties:{info}}});
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };

test('completed assistant generation emits one llm span with fresh and cache separated', async () => {
  const msg = {
    id:'m1', sessionID:'s1', role:'assistant', modelID:'gpt-6-luna',
    providerID:'openai', time:{created:1793790000000, completed:1793790003000},
    tokens:{input:8,output:6,reasoning:3,cache:{read:20,write:4}},
    cost:0.0123, finish:'stop', content:'SECRET_PROMPT_SHOULD_NOT_LEAK',
  };
  await event(msg); await flush();
  const llm = calls.filter(c => c.url.endsWith('/spans') && c.body.type === 'llm');
  assert.equal(llm.length, 1);
  const x = llm[0].body;
  assert.equal(x.model, 'gpt-6-luna');
  assert.equal(x.provider, 'openai');
  assert.deepEqual(x.usage, {
    prompt_tokens:32,completion_tokens:9,total_tokens:41,
    input_tokens:8,output_tokens:6,cache_read_tokens:20,
    cache_write_tokens:4,reasoning_tokens:3,
  });
  assert.equal(x.metadata.provider_reported_cost_usd, 0.0123);
  assert.equal(x.metadata.paperclip_run_id, process.env.PAPERCLIP_RUN_ID);
  assert.ok(!JSON.stringify(x).includes('SECRET_PROMPT_SHOULD_NOT_LEAK'));
  await event(msg); await flush();
  assert.equal(calls.filter(c => c.body.type === 'llm').length,1,'duplicate completion must not double count');
});

test('incomplete assistant and user messages must not emit generation spans', async () => {
  await event({id:'m2',role:'assistant',time:{created:1793790000000}});
  await event({id:'m3',role:'user',time:{completed:1793790003000}});
  await flush();
  assert.equal(calls.filter(c => c.body.type === 'llm').length,1);
});

test('tool traces still emitted after instrumenting model generations', async () => {
  const input={tool:'read',args:{id:'x'}};
  await plugin['tool.execute.before'](input,{});
  await plugin['tool.execute.after'](input,{output:{ok:true}});
  await flush();
  const toolSpans = calls.filter(c => c.url.endsWith('/spans') && c.body.name === 'read');
  assert.equal(toolSpans.length,1);
  assert.equal(toolSpans[0].body.type,'tool','Opik tool spans must be typed for downstream metrics');
});

test('session idle still finalizes the trace', async () => {
  await plugin.event({event:{type:'session.idle'}});
  await flush();
  assert.equal(calls.filter(c => c.url.includes('/traces/') && c.body.end_time).length,1);
});


test('transient 503 is retried and never treated as successful ingestion', async () => {
  failNext = 1; failedKind = '/spans';
  await event({
    id:'retry1', sessionID:'s1', role:'assistant', modelID:'gpt-6-luna',
    providerID:'openai', time:{created:1793790000000,completed:1793790003000},
    tokens:{input:3,output:2,cache:{read:0,write:0}},
  });
  assert.equal(calls.filter(x => x.body.metadata?.open_code_message_id === 'retry1').length,2);
  const accepted=calls.filter(x => x.body.type==='llm'&&x.body.metadata?.open_code_message_id==='retry1');
  assert.equal(accepted[0].body.trace_id,accepted[1].body.trace_id);
});
test('session error emits non-secret structured lifecycle status', async () => {
  await plugin.event({event:{type:'session.error',properties:{
    error:{name:'ProcessLost',message:'DO_NOT_LOG_SECRET'}
  }}});
  const patches=calls.filter(x=>x.url.includes('/traces/')&&x.body.metadata?.end_event==='session.error');
  // If already idle-finalized, the run has a single terminal event.
  assert.ok(patches.length===0 || (patches.length===1 &&
    patches[0].body.metadata.error_type==='ProcessLost'));
  assert.ok(!JSON.stringify(patches).includes('DO_NOT_LOG_SECRET'));
});
test('Opik root trace retains source and billing provenance', async () => {
  const root=calls.find(x=>x.url.endsWith('/traces')&&x.body.metadata?.paperclip_run_id);
  assert.ok(root);
  assert.equal(root.body.metadata.service,'paperclip-opencode');
  assert.equal(root.body.metadata.billing_status,'unknown_until_verified');
});


test('privacy gate: tool arguments and output never leave agent, even with capture env enabled', async () => {
  process.env.OPIK_CAPTURE_TOOL_PAYLOADS = 'true';
  const input = {tool:'read',args:{
    auth:'Bearer TOOL_ARGS_PRIVATE_987',nested:{privateNote:'USER_CONTENT_PRIVATE_654'},
  }};
  const before = calls.length;
  await plugin['tool.execute.before'](input,{args:{token:'OUTPUT_ARGS_PRIVATE_987'}});
  await plugin['tool.execute.after'](input,{output:{
    message:'TOOL_RESPONSE_PRIVATE_321',deep:{accessToken:'SECRETS_PRIVATE_000'}
  }});
  const emitted = calls.slice(before).filter(c=>c.body.type==='tool');
  assert.equal(emitted.length,1);
  const serialized = JSON.stringify(emitted[0].body);
  for (const secret of ['TOOL_ARGS_PRIVATE_987','USER_CONTENT_PRIVATE_654','OUTPUT_ARGS_PRIVATE_987',
                        'TOOL_RESPONSE_PRIVATE_321','SECRETS_PRIVATE_000']) {
    assert.ok(!serialized.includes(secret), 'payload leakage: '+secret);
  }
  assert.deepEqual(emitted[0].body.input,{tool:'read'});
  assert.equal(emitted[0].body.output.status,'completed');
  assert.equal(typeof emitted[0].body.output.duration_ms,'number');
  delete process.env.OPIK_CAPTURE_TOOL_PAYLOADS;
});

test('unsafe dynamic tool name is replaced with an unclassified identifier', async () => {
  const input={tool:'Bearer should-not-ever-be-here',args:{raw:'PRIVATE_BLOB_111'}};
  await plugin['tool.execute.before'](input,{});
  await plugin['tool.execute.after'](input,{error:{message:'PRIVATE_BLOB_222'}});
  const matches=calls.filter(c=>c.body.type==='tool'&&c.body.name==='unknown_tool');
  assert.equal(matches.length,1);
  assert.equal(matches[0].body.output.status,'error');
  assert.ok(!JSON.stringify(matches[0].body).includes('PRIVATE_BLOB_'));
});

test('token-shaped identifiers and dynamic MCP names are never emitted verbatim', async () => {
  const cases = [
    ['sk_live_ABC123456789abcdef', 'unknown_tool'],
    ['ghp_0123456789ABCDEFGHIJKLMN', 'unknown_tool'],
    ['CANARY_TOKEN_IDENTIFIER_999999', 'unknown_tool'],
    ['mcp__PC__fakeTokenNamed_ABC987654', 'mcp_tool'],
    ['paperclip_tokenValueABC123456', 'paperclip_tool'],
    ['hindsight_privateBankKey_987654', 'hindsight_tool'],
    ['github_secretSource12345', 'github_tool'],
    ['some_valid_but_untrusted_tool_name', 'unknown_tool'],
  ];
  for (const [name,expected] of cases) {
    const before=calls.length;
    const input={tool:name,args:{secret:'SYNTHETIC_ARG_NEVER_LOG'}};
    await plugin['tool.execute.before'](input,{});
    await plugin['tool.execute.after'](input,{output:'SYNTHETIC_RESPONSE_NEVER_LOG'});
    const sent=calls.slice(before).filter(c=>c.body.type==='tool');
    assert.equal(sent.length,1);
    assert.equal(sent[0].body.name,expected);
    assert.equal(sent[0].body.input.tool,expected);
    const payload=JSON.stringify(sent[0].body);
    assert.ok(!payload.includes(name),'untrusted identifier leaked');
    assert.ok(!payload.includes('SYNTHETIC_ARG_NEVER_LOG'));
    assert.ok(!payload.includes('SYNTHETIC_RESPONSE_NEVER_LOG'));
  }
});

test('HTTP 307/308 redirects fail closed with zero target replay', async () => {
  const priorFetch = globalThis.fetch;
  const priorBase = process.env.OPIK_BASE_URL;
  try {
    for (const redirectStatus of [307, 308]) {
      let targetHits = 0;
      let redirectHits = 0;
      const target = createServer((_req,res) => { targetHits++; res.writeHead(200); res.end('UNSAFE'); });
      await new Promise(resolve => target.listen(0, '127.0.0.1', resolve));
      const dst = 'http://127.0.0.1:' + target.address().port + '/redirect-target';
      const redirector = createServer((_req,res) => {
        redirectHits++;
        res.writeHead(redirectStatus, {'Location': dst}); res.end();
      });
      await new Promise(resolve => redirector.listen(0, '127.0.0.1', resolve));
      try {
        process.env.OPIK_BASE_URL = 'http://127.0.0.1:' + redirector.address().port;
        globalThis.fetch = nativeFetch;
        const {default:canaryFactory} = await import('./index.mjs?redirect-negative-' + redirectStatus);
        const canary = await canaryFactory();
        await canary.event({event:{type:'session.idle'}});
        assert.ok(redirectHits > 0, 'redirect endpoint was exercised');
        assert.equal(targetHits, 0, String(redirectStatus) + ' must not replay the request body to target');
      } finally {
        await new Promise(resolve => { redirector.close(resolve); redirector.closeAllConnections?.(); });
        await new Promise(resolve => { target.close(resolve); target.closeAllConnections?.(); });
      }
    }
  } finally {
    globalThis.fetch = priorFetch;
    if (priorBase === undefined) delete process.env.OPIK_BASE_URL;
    else process.env.OPIK_BASE_URL = priorBase;
  }
});
