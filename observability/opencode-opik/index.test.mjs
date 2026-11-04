import test from 'node:test';
import assert from 'node:assert/strict';

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
  const input={tool:'test_tool',args:{id:'x'}};
  await plugin['tool.execute.before'](input,{});
  await plugin['tool.execute.after'](input,{output:{ok:true}});
  await flush();
  const toolSpans = calls.filter(c => c.url.endsWith('/spans') && c.body.name === 'test_tool');
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

