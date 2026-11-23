import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeServer, deleteRefWithLease, casDeleteArgs } from '../server.mjs';
const REPO='jtrtdhrst/harness-zar-i-szlif', SHA='a'.repeat(40);
async function fixture({writesEnabled=false,allowDeletion=false, githubToken='x',writerToken='',callerToken='my-private-token',
  branchSHA=SHA,ahead=0,protectedBranch=false,approved=true,merged=true,openPR=false,mergeReachable=true,dispatchRunSHA=SHA,dispatchRunId=true,run404Count=0,
  deployments=[],rulesets=[],deploymentsInvalid=false,rulesetsInvalid=false,classicProtectionMissing=false,
  rulesStatus=200,rulesList=[],rulesMessage='Forbidden',pushToken='',pinnedBranches,pushRemoteFor,gitBin,liveRef=null,liveBranch='fix/old'}={}){
  const calls=[];
  const authorizations=[];
  let branchDeleted=false;
  let runReadsToMiss=run404Count;
  const mergeSHA='c'.repeat(40);
  const {execFileSync}=await import('node:child_process');
  const liveSHA=()=>{
    if(!liveRef)return null;
    try{return execFileSync('git',['--git-dir',liveRef,'rev-parse','--verify',`refs/heads/${liveBranch}`],{encoding:'utf8',stdio:['ignore','pipe','ignore']}).trim();}
    catch{return null;}
  };
  const fake=async(url,opts)=>{
    const u=new URL(url);calls.push([opts.method,u.pathname+u.search]);authorizations.push(opts.headers.Authorization);
    if(classicProtectionMissing && u.pathname.endsWith('/branches/main/protection')) return new Response(JSON.stringify({message:'Branch not protected'}),{status:404});
    let v={};
    if(opts.method==='DELETE'&&u.pathname.includes('/git/refs/heads/')){
      branchDeleted=true;
      return new Response(null,{status:204});
    }
    if(u.pathname.includes('/rules/branches/')){
      if(rulesStatus!==200)return new Response(JSON.stringify({message:rulesMessage}),{status:rulesStatus,headers:{'content-type':'application/json'}});
      v=rulesList;
    }
    else if(u.pathname.endsWith('/branches/main'))v={commit:{sha:SHA}};
    else if(u.pathname.includes('/branches/')){
      if(liveRef){
        const sha=liveSHA();
        if(!sha)return new Response(null,{status:404});
        v={commit:{sha},protected:protectedBranch};
      }else if(branchDeleted)return new Response(null,{status:404});
      else v={commit:{sha:branchSHA},protected:protectedBranch};
    }
    else if(u.pathname.endsWith('/pulls')){
      if(u.searchParams.get('state')==='open')
        v=openPR?[{base:{ref:'fix/old'},head:{ref:'fix/old',repo:{full_name:REPO}}}]:[];
      else
        v=merged?[{number:987,merged_at:'2026-11-20T12:00:00Z',
          head:{ref:'fix/old',sha:branchSHA,repo:{full_name:REPO}},base:{ref:'main'},merge_commit_sha:mergeSHA}]:[];
    }
    else if(u.pathname.includes('/compare/'))v={ahead_by:ahead,behind_by:mergeReachable?0:1};
    else if(u.pathname.endsWith('/actions/runs/321')){
      if(runReadsToMiss-- >0)return new Response(null,{status:404});
      v={id:321,head_sha:dispatchRunSHA,event:'workflow_dispatch',path:'.github/workflows/release-lanes-policy.yml',html_url:'https://github.com/example/actions/runs/321'};
    }
    else if(u.pathname.endsWith('/actions/runs/123'))v={head_sha:SHA,status:'in_progress',path:'.github/workflows/release-lanes-policy.yml'};
    else if(u.pathname.endsWith(`/repos/${REPO}`))v={full_name:REPO,default_branch:'main',permissions:{push:true}};
    if(opts.method==='POST'&&u.pathname.endsWith('/dispatches'))
      return new Response(dispatchRunId?JSON.stringify({workflow_run_id:321}):null,
        {status:dispatchRunId?200:204,headers:{'content-type':'application/json'}});
    if(u.pathname.endsWith('/deployments'))v=deploymentsInvalid?{}:deployments;
    else if(u.pathname.endsWith('/rulesets'))v=rulesetsInvalid?{}:rulesets;
    else if(u.pathname.endsWith('/actions/permissions'))v={enabled:true,allowed_actions:'all'};
    return new Response(opts.method==='POST'?null:JSON.stringify(v),{status:opts.method==='POST'?204:200,headers:{'content-type':'application/json'}});
  };
  const s=makeServer({fetchImpl:fake,githubToken,writerToken,callerToken,writesEnabled,allowDeletion,
    pushToken,pinnedBranches,pushRemoteFor,gitBin,
    deletionAllowlist:approved?[`${REPO}:fix/old@${SHA}`,`${REPO}:fix/old@${branchSHA}`]:[],workflows:['release-lanes-policy.yml'],dispatchPollDelayMs:1});
  await new Promise(resolve=>s.listen(0,'127.0.0.1',resolve));
  const root=`http://127.0.0.1:${s.address().port}`;
  const request=async(name,args={},auth=true)=>{
    const x=await fetch(root+'/mcp',{method:'POST',headers:{'content-type':'application/json',...(auth?{authorization:`Bearer ${callerToken}`}:{})},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name,arguments:args}})});
    return {http:x.status,body:await x.json()};
  };
  return {s,root,calls,authorizations,request,close:()=>new Promise(r=>s.close(r))};
}
test('real HTTP MCP initialize/list + no token denied',async()=>{
  const f=await fixture();try{
    const x=await f.request('github_repo_info',{repo:REPO},false);assert.equal(x.http,401);
    const y=await fetch(f.root+'/mcp',{method:'POST',headers:{authorization:'Bearer my-private-token'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'})});
    assert.equal((await y.json()).result.tools.length,20);
  }finally{await f.close()}
});
test('tool metadata requires OAuth for all twenty tools',async()=>{
 const f=await fixture();try{
  const response=await fetch(f.root+'/mcp',{method:'POST',headers:{authorization:'Bearer my-private-token'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'})});
  const tools=(await response.json()).result.tools;
  assert.equal(tools.length,20);
  for(const tool of tools){
    assert.deepEqual(tool.securitySchemes,[{type:'oauth2',scopes:[]}]);
    assert.deepEqual(tool._meta.securitySchemes,[{type:'oauth2',scopes:[]}]);
  }
 }finally{await f.close()}
});
test('missing bearer returns protected resource OAuth challenge and no provider traffic',async()=>{
 const f=await fixture();try{
  const response=await fetch(f.root+'/mcp',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'})});
  assert.equal(response.status,401);
  assert.match(response.headers.get('www-authenticate'),/^Bearer resource_metadata="https:\/\/github-ops-mcp\.zariszlif\.pl\/\.well-known\/oauth-protected-resource\/mcp"/);
  assert.equal((await response.json()).error,'invalid_token');
  assert.equal(f.calls.length,0);
 }finally{await f.close()}
});
test('GET /mcp has protocol-appropriate 405 rather than misleading 404',async()=>{
 const f=await fixture();try{
  const response=await fetch(f.root+'/mcp');
  assert.equal(response.status,405);
  assert.equal(response.headers.get('allow'),'POST');
 }finally{await f.close()}
});
test('repo allowlist and live read',async()=>{
  const f=await fixture();try{
    assert.equal((await f.request('github_repo_info',{repo:REPO})).body.result.structuredContent.full_name,REPO);
    assert.match((await f.request('github_repo_info',{repo:'someone/private'})).body.result.content[0].text,/REPO_DENIED/);
    assert.equal(f.calls.length,1);
  }finally{await f.close()}
});
test('no GitHub token fails closed',async()=>{
  const f=await fixture({githubToken:''});try{
    const x=await f.request('github_repo_info',{repo:REPO});assert.match(x.body.result.content[0].text,/AUTH_NOT_CONFIGURED/);assert.equal(f.calls.length,0);
  }finally{await f.close()}
});
test('preview rejects nonmerged, stale and protected branches without DELETE',async()=>{
 for(const opt of [{merged:false,err:'MERGE_NOT_VERIFIED'},{branchSHA:'b'.repeat(40),err:'STALE_SHA'},{protectedBranch:true,err:'PROTECTED'}]){
  const f=await fixture(opt);
  try {
   const x=await f.request('github_preview_branch_delete',{repo:REPO,branch:'fix/old',expected_sha:SHA});
   assert.match(x.body.result.content[0].text,new RegExp(opt.err));
   assert.equal(f.calls.some(([method])=>method==='DELETE'),false);
  }finally{await f.close()}
 }
});
test('deletion is advertised but fails closed before any traffic without writes or push credential',async()=>{
 const f=await fixture({writesEnabled:true,allowDeletion:true});
 try{
  const list=await fetch(f.root+'/mcp',{method:'POST',headers:{authorization:'Bearer my-private-token'},
    body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'})});
  assert.equal((await list.json()).result.tools.some(t=>t.name==='github_delete_merged_branch'),true,'the CAS delete must be advertised');
  const x=await f.request('github_delete_merged_branch',{repo:REPO,branch:'fix/old',expected_sha:SHA});
  assert.match(x.body.result.content[0].text,/PUSH_CREDENTIAL_MISSING/);
  assert.equal(f.calls.length,0,'no provider traffic before the credential gate');
 }finally{await f.close()}
});
test('deletion never runs with writes disabled even when a push credential exists',async()=>{
 const f=await fixture({writesEnabled:false,pushToken:'test-push-token'});
 try{
  const x=await f.request('github_delete_merged_branch',{repo:REPO,branch:'fix/old',expected_sha:SHA});
  assert.match(x.body.result.content[0].text,/WRITE_DISABLED/);
  assert.equal(f.calls.length,0);
 }finally{await f.close()}
});
test('open PR and unreachable merge commit prevent preview',async()=>{
 for(const opt of [{openPR:true,err:'OPEN_PR'},{mergeReachable:false,err:'MERGE_NOT_REACHABLE'}]){
  const f=await fixture(opt);
  try{
   const x=await f.request('github_preview_branch_delete',{repo:REPO,branch:'fix/old',expected_sha:SHA});
   assert.match(x.body.result.content[0].text,new RegExp(opt.err));
  }finally{await f.close()}
 }
});
test('squash-merged PR is eligible for preview only, never deletes',async()=>{
 const f=await fixture({ahead:9});
 try{
  const out=await f.request('github_preview_branch_delete',{repo:REPO,branch:'fix/old',expected_sha:SHA});
  assert.equal(out.body.result.structuredContent.eligible,true);
  assert.equal(out.body.result.structuredContent.deletion_supported,false);
  assert.equal(out.body.result.structuredContent.merged_pr,987);
  assert.equal(f.calls.filter(([method])=>method==='DELETE').length,0);
 }finally{await f.close()}
});
test('staging and known live Coolify branch are never eligible',async()=>{
 const f=await fixture();
 try{
  for(const branch of ['ZARI-155','staging/github-ops','hold/release','operator/safety']){
   const out=await f.request('github_preview_branch_delete',{repo:REPO,branch,expected_sha:SHA});
   assert.match(out.body.result.content[0].text,/BRANCH_DENIED/);
  }
  assert.equal(f.calls.length,0);
 }finally{await f.close()}
});
test('workflow dispatch is unavailable even with write flag enabled',async()=>{
  const f=await fixture({writesEnabled:true});try{
    const list=await fetch(f.root+'/mcp',{method:'POST',headers:{authorization:'Bearer my-private-token'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'})});
    assert.equal((await list.json()).result.tools.some(t=>t.name==='github_dispatch_workflow'),false);
    const out=await f.request('github_dispatch_workflow',{repo:REPO,workflow:'release-lanes-policy.yml',expected_sha:SHA});
    assert.match(out.body.result.content[0].text,/TOOL_UNKNOWN/);
    assert.equal(f.calls.length,0);
  }finally{await f.close()}
});

test('run cancellation exact SHA and allowlisted flow',async()=>{
 const f=await fixture({writesEnabled:true,writerToken:'writer-test'});try{
    assert.match((await f.request('github_cancel_workflow_run',{repo:REPO,run_id:123,expected_sha:'b'.repeat(40)})).body.result.content[0].text,/STALE_SHA/);
    assert.equal((await f.request('github_cancel_workflow_run',{repo:REPO,run_id:123,expected_sha:SHA})).body.result.structuredContent.cancel_requested,true);
 }finally{await f.close()}
});
test('read-only tools fail closed for missing provider admin rights',async()=>{
 const f=await fixture();try{
    for(const name of ['github_get_rulesets','github_get_actions_permissions','github_get_branch_protection'])assert.ok((await f.request(name,{repo:REPO})).body.result.structuredContent);
 }finally{await f.close()}
});

test('Cloudflare Access RS256 JWT accepts owner but rejects forgery and wrong claims',async()=>{
 const {generateKeyPairSync,sign}=await import('node:crypto');
 const {privateKey,publicKey}=generateKeyPairSync('rsa',{modulusLength:2048});
 const jwk={...publicKey.export({format:'jwk'}),kid:'test-kid',alg:'RS256',use:'sig'};
 const issuer='https://example.cloudflareaccess.com', audience='example-aud', now=Math.floor(Date.now()/1000);
 const jwt=(extra={},forged=false)=>{
   const hdr=Buffer.from(JSON.stringify({alg:'RS256',typ:'JWT',kid:'test-kid'})).toString('base64url');
   const body=Buffer.from(JSON.stringify({iss:issuer,aud:audience,email:'owner@example.com',iat:now-10,nbf:now-10,exp:now+600,...extra})).toString('base64url');
   const data=hdr+'.'+body;
   const sig=sign('RSA-SHA256',Buffer.from(data),privateKey).toString('base64url');
   return data+'.'+(forged?'a'.repeat(64):sig);
 };
 let reads=0;
 const server=makeServer({
   callerToken:'',githubToken:'gh-test',accessIssuer:issuer,accessAudience:audience,accessOwnerEmail:'owner@example.com',
   accessFetchImpl:async()=>new Response(JSON.stringify({keys:[jwk]}),{status:200}),
   fetchImpl:async()=>{reads++;return new Response(JSON.stringify({full_name:REPO,default_branch:'main'}),{status:200})}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const root='http://127.0.0.1:'+server.address().port;
 const call=async(token)=>{
   const res=await fetch(root+'/mcp',{method:'POST',headers:{'content-type':'application/json',...(token?{'cf-access-jwt-assertion':token}:{})},
     body:JSON.stringify({jsonrpc:'2.0',id:42,method:'tools/call',params:{name:'github_repo_info',arguments:{repo:REPO}}})});
   return {status:res.status,body:await res.json()};
 };
 try{
   assert.equal((await call('')).status,401);
   assert.equal((await call(jwt())).body.result.structuredContent.full_name,REPO);
   assert.equal(reads,1);
   for(const bad of [jwt({aud:'wrong'}),jwt({email:'attacker@example.com'}),jwt({iss:'https://evil.cloudflareaccess.com'}),jwt({exp:now-1}),jwt({},true)]){
     assert.equal((await call(bad)).status,401);
   }
   assert.equal(reads,1,'invalid requests never reach GitHub');
 }finally{await new Promise(resolve=>server.close(resolve))}
});

// Regression: PR #169 live defect. GitHub REST returns a bare array (empty when no
// deployment exists at that SHA). MCP structuredContent MUST be an object, otherwise
// the connector rejects the result with "structuredContent expects dictionary, got []".
const isPlainObject=v=>Boolean(v)&&typeof v==='object'&&!Array.isArray(v);
async function toolsListed(root){
  const res=await fetch(root+'/mcp',{method:'POST',headers:{authorization:'Bearer my-private-token'},
    body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'})});
  return (await res.json()).result.tools;
}
test('empty deployment list returns object structuredContent over HTTP',async()=>{
  const f=await fixture({deployments:[]});
  try{
    const out=await f.request('github_get_deployments',{repo:REPO,sha:SHA});
    assert.equal(out.http,200);
    const result=out.body.result;
    assert.equal(result.isError,undefined);
    assert.equal(isPlainObject(result.structuredContent),true,'structuredContent must be a dictionary');
    assert.deepEqual(result.structuredContent,{repo:REPO,sha:SHA,count:0,deployments:[]});
    assert.deepEqual(JSON.parse(result.content[0].text),result.structuredContent);
    const deploymentsCall=f.calls.find(([,path])=>path.includes('/deployments'));
    assert.ok(deploymentsCall[1].includes(`sha=${SHA}`),'exact SHA is forwarded lowercased');
  }finally{await f.close()}
});
test('non-empty deployment list keeps the same object envelope',async()=>{
  const f=await fixture({deployments:[{id:7,sha:SHA,environment:'production'}]});
  try{
    const out=await f.request('github_get_deployments',{repo:REPO,sha:SHA.toUpperCase()});
    assert.equal(isPlainObject(out.body.result.structuredContent),true);
    assert.equal(out.body.result.structuredContent.count,1);
    assert.equal(out.body.result.structuredContent.deployments[0].id,7);
  }finally{await f.close()}
});
test('empty ruleset list is also wrapped in an object',async()=>{
  const f=await fixture({rulesets:[]});
  try{
    const out=await f.request('github_get_rulesets',{repo:REPO});
    assert.equal(isPlainObject(out.body.result.structuredContent),true);
    assert.deepEqual(out.body.result.structuredContent,{repo:REPO,rulesets:[],count:0});
  }finally{await f.close()}
});
test('invalid provider list shape fails closed instead of emitting a bare array',async()=>{
  for(const opt of [{deploymentsInvalid:true,name:'github_get_deployments',args:{repo:REPO,sha:SHA},code:'DEPLOYMENTS_INVALID'},
                    {rulesetsInvalid:true,name:'github_get_rulesets',args:{repo:REPO},code:'RULESETS_INVALID'}]){
    const f=await fixture(opt);
    try{
      const out=await f.request(opt.name,opt.args);
      assert.equal(out.body.result.isError,true);
      assert.match(out.body.result.content[0].text,new RegExp(opt.code));
      assert.equal(out.body.result.structuredContent,undefined);
    }finally{await f.close()}
  }
});
test('every advertised tool returns object structuredContent, never a bare array',async()=>{
  const b=await bareWithBranch();
  const f=await fixture({writesEnabled:true,writerToken:'writer-test',deployments:[],rulesets:[],branchSHA:b.sha,
    liveRef:b.bare,liveBranch:'fix/old',pushToken:'test-push-token',pushRemoteFor:()=>b.url});
  try{
    const tools=await toolsListed(f.root);
    assert.equal(tools.length,20);
    assert.equal(tools.some(t=>t.name==='github_dispatch_workflow'),false,'removed dispatch must stay unadvertised');
    const args={github_repo_info:{repo:REPO},github_get_rulesets:{repo:REPO},
      github_get_actions_permissions:{repo:REPO},github_get_branch_protection:{repo:REPO},
      github_get_deployments:{repo:REPO,sha:SHA},
      github_preview_branch_delete:{repo:REPO,branch:'fix/old',expected_sha:b.sha},
      github_delete_merged_branch:{repo:REPO,branch:'fix/old',expected_sha:b.sha},
      github_cancel_workflow_run:{repo:REPO,run_id:123,expected_sha:SHA}};
    for(const tool of tools.filter(t=>Object.hasOwn(args,t.name))){
      const out=await f.request(tool.name,args[tool.name]);
      assert.equal(out.http,200,tool.name);
      assert.equal(out.body.result.isError,undefined,tool.name+' must not error: '+JSON.stringify(out.body.result).slice(0,300));
      assert.equal(isPlainObject(out.body.result.structuredContent),true,tool.name+' structuredContent must be a dictionary');
      assert.deepEqual(JSON.parse(out.body.result.content[0].text),out.body.result.structuredContent,tool.name+' text and structured content agree');
    }
  }finally{await f.close();b.cleanup()}
});
test('legacy dispatch tool call is rejected over HTTP and advertises no dispatch input',async()=>{
  const f=await fixture({writesEnabled:true});
  try{
    const tools=await toolsListed(f.root);
    for(const tool of tools)assert.equal(Object.hasOwn(tool.inputSchema.properties,'workflow'),false,tool.name+' exposes no dispatch argument');
    const out=await f.request('github_dispatch_workflow',{repo:REPO,workflow:'release-lanes-policy.yml',expected_sha:SHA});
    assert.equal(out.http,200);
    assert.equal(out.body.result.isError,true);
    assert.match(out.body.result.content[0].text,/TOOL_UNKNOWN/);
    assert.match(out.body.result.content[0].text,/Re-initialize the client tool list/);
    assert.equal(f.calls.some(([,path])=>path.includes('/dispatches')),false,'no provider dispatch traffic');
  }finally{await f.close()}
});

// --- CAS branch deletion (ZARI-263) -----------------------------------------
// GitHub REST DELETE /git/refs has no expected-SHA precondition. The git
// receive-pack protocol does: --force-with-lease sends the expected oid and the
// server refuses the delete if the ref moved. These tests exercise that path
// against a real, isolated bare remote — no network, no GitHub credential.

async function bareWithBranch(branch = 'fix/old') {
  const { execFileSync } = await import('node:child_process');
  const { mkdtempSync, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const root = mkdtempSync(join(tmpdir(), 'ghops-test-'));
  const bare = join(root, 'remote.git'), work = join(root, 'work');
  const env = { ...process.env, GIT_CONFIG_NOSYSTEM: '1',
    GIT_AUTHOR_NAME: 't', GIT_AUTHOR_EMAIL: 't@example.invalid',
    GIT_COMMITTER_NAME: 't', GIT_COMMITTER_EMAIL: 't@example.invalid' };
  const run = (cwd, ...args) => execFileSync('git', args, { cwd, encoding: 'utf8', env, stdio: ['ignore', 'pipe', 'pipe'] });
  run(root, 'init', '--bare', '-q', bare);
  run(root, 'init', '-q', work);
  run(work, 'checkout', '-q', '-b', branch);
  run(work, 'commit', '-q', '--allow-empty', '-m', 'first');
  const sha = run(work, 'rev-parse', 'HEAD').trim();
  run(work, 'push', '-q', bare, `HEAD:refs/heads/${branch}`);
  return {
    root, bare, work, branch, sha, url: `file://${bare}`,
    advance() {
      run(work, 'commit', '-q', '--allow-empty', '-m', 'second');
      const next = run(work, 'rev-parse', 'HEAD').trim();
      run(work, 'push', '-q', bare, `HEAD:refs/heads/${branch}`);
      return next;
    },
    ref() {
      try { return run(root, '--git-dir', bare, 'rev-parse', '--verify', `refs/heads/${branch}`).trim(); }
      catch { return null; }
    },
    cleanup() { try { rmSync(root, { recursive: true, force: true }); } catch {} },
  };
}

test('CAS argv pins the exact expected SHA and carries no secret', async () => {
  const argv = casDeleteArgs({ remote: 'https://github.com/o/r.git', branch: 'fix/old', expectedSha: SHA });
  assert.deepEqual(argv, ['push', '--porcelain', `--force-with-lease=refs/heads/fix/old:${SHA}`,
    'https://github.com/o/r.git', ':refs/heads/fix/old']);
  assert.equal(argv.some(a => a.includes('ghp_') || a.includes('token')), false);
  assert.throws(() => casDeleteArgs({ remote: 'https://attacker.invalid/o/r.git', branch: 'fix/old', expectedSha: SHA }),
    e => e.code === 'REMOTE_INVALID');
  assert.throws(() => casDeleteArgs({ remote: 'https://github.com@attacker.invalid/o/r.git', branch: 'fix/old', expectedSha: SHA }),
    e => e.code === 'REMOTE_INVALID');
  assert.throws(() => casDeleteArgs({ remote: 'http://plaintext.example/r.git', branch: 'fix/old', expectedSha: SHA }),
    e => e.code === 'REMOTE_INVALID');
});

test('git lease rejects a stale expected SHA and keeps the ref', async () => {
  const b = await bareWithBranch();
  try {
    const stale = await deleteRefWithLease({ remote: b.url, branch: 'fix/old', expectedSha: 'b'.repeat(40), pushToken: 'unused' });
    assert.equal(stale.accepted, false);
    assert.equal(stale.code, 'STALE_LEASE_REJECTED');
    assert.equal(b.ref(), b.sha, 'a refused lease must leave the ref untouched');
    const ok = await deleteRefWithLease({ remote: b.url, branch: 'fix/old', expectedSha: b.sha, pushToken: 'unused' });
    assert.equal(ok.accepted, true);
    assert.equal(b.ref(), null, 'the exact-SHA lease deletes the ref');
  } finally { b.cleanup(); }
});

test('deletion refuses stale SHA, protection, rules and unknown rule state without touching the ref', async () => {
  const cases = [
    { opt: { branchSHA: 'b'.repeat(40) }, err: 'STALE_SHA' },
    { opt: { protectedBranch: true }, err: 'PROTECTED' },
    { opt: { rulesList: [{ type: 'deletion' }] }, err: 'RULES_PRESENT' },
    { opt: { rulesStatus: 403 }, err: 'RULES_UNAVAILABLE' },
    { opt: { merged: false }, err: 'MERGE_NOT_VERIFIED' },
    { opt: { openPR: true }, err: 'OPEN_PR' },
  ];
  for (const { opt, err } of cases) {
    const f = await fixture({ writesEnabled: true, pushToken: 'test-push-token', gitBin: '/nonexistent/git', ...opt });
    try {
      const x = await f.request('github_delete_merged_branch', { repo: REPO, branch: 'fix/old', expected_sha: SHA });
      assert.match(x.body.result.content[0].text, new RegExp(err));
      assert.equal(x.body.result.isError, true);
      assert.equal(f.calls.some(([method]) => method === 'DELETE'), false, 'no REST DELETE is ever issued');
    } finally { await f.close(); }
  }
});

test('a plan-limited rulesets endpoint is not treated as unknown protection', async () => {
  // Private repository without GitHub Pro: rulesets cannot exist at all. The
  // branch's own `protected` flag (checked earlier) is the authoritative
  // classic-protection signal, so deletion proceeds — but any other 403 stays
  // fail-closed (covered by the RULES_UNAVAILABLE case above).
  const b = await bareWithBranch();
  const f = await fixture({ writesEnabled: true, pushToken: 'test-push-token', branchSHA: b.sha,
    liveRef: b.bare, liveBranch: 'fix/old', pushRemoteFor: () => b.url,
    rulesStatus: 403, rulesMessage: 'Upgrade to GitHub Pro or make this repository public to enable this feature.' });
  try {
    const out = await f.request('github_delete_merged_branch', { repo: REPO, branch: 'fix/old', expected_sha: b.sha });
    assert.equal(out.body.result.isError, undefined, JSON.stringify(out.body.result));
    assert.equal(out.body.result.structuredContent.rules, 'unavailable_on_plan');
    assert.equal(b.ref(), null);
  } finally { await f.close(); b.cleanup(); }
});

test('a Coolify-pinned branch is refused even when every other gate would pass', async () => {
  const b = await bareWithBranch('feat/github-ops-mcp-20261120');
  const f = await fixture({ writesEnabled: true, pushToken: 'test-push-token', branchSHA: b.sha,
    liveRef: b.bare, liveBranch: b.branch, pushRemoteFor: () => b.url });
  try {
    const x = await f.request('github_delete_merged_branch', { repo: REPO, branch: b.branch, expected_sha: b.sha });
    assert.match(x.body.result.content[0].text, /BRANCH_PINNED/);
    assert.equal(b.ref(), b.sha, 'the pinned ref survives');
    assert.equal(f.calls.length, 0, 'refused before any provider traffic');
  } finally { await f.close(); b.cleanup(); }
});

test('deletion reads back the removed ref instead of trusting the push', async () => {
  const b = await bareWithBranch();
  const f = await fixture({ writesEnabled: true, pushToken: 'test-push-token', branchSHA: b.sha,
    liveRef: b.bare, liveBranch: 'fix/old', pushRemoteFor: () => b.url });
  try {
    const out = await f.request('github_delete_merged_branch', { repo: REPO, branch: 'fix/old', expected_sha: b.sha });
    assert.equal(out.body.result.isError, undefined, JSON.stringify(out.body.result));
    assert.equal(out.body.result.structuredContent.deleted, true);
    assert.equal(out.body.result.structuredContent.lease, 'force-with-lease');
    assert.equal(out.body.result.structuredContent.merged_pr, 987);
    assert.equal(b.ref(), null);
    assert.equal(f.calls.some(([method]) => method === 'DELETE'), false, 'deletion never goes through REST DELETE');
  } finally { await f.close(); b.cleanup(); }
});

test('a push that lands between verification and delete is rejected by the lease', async () => {
  const b = await bareWithBranch();
  // The API view is pinned to the pre-race SHA, exactly as it would be if a
  // push landed after the checks; the real ref has moved on.
  const f = await fixture({ writesEnabled: true, pushToken: 'test-push-token', branchSHA: b.sha, pushRemoteFor: () => b.url });
  try {
    const movedTo = b.advance();
    const out = await f.request('github_delete_merged_branch', { repo: REPO, branch: 'fix/old', expected_sha: b.sha });
    assert.match(out.body.result.content[0].text, /STALE_LEASE_REJECTED/);
    assert.equal(b.ref(), movedTo, 'the concurrent commit is preserved, never overwritten');
  } finally { await f.close(); b.cleanup(); }
});


test('GitHub App role token file is validated, rotated and fail-closed', async()=>{
 const {mkdtempSync,writeFileSync,chmodSync,rmSync}=await import('node:fs');
 const {tmpdir}=await import('node:os');const {join}=await import('node:path');
 const dir=mkdtempSync(join(tmpdir(),'github-ops-role-')),file=join(dir,'reader.json');
 const seen=[];
 const role=(token,permissions={actions:'read',administration:'read',contents:'read',deployments:'read',metadata:'read'})=>({
  token,role:'github-ops-reader',app_id:5398752,installation_id:173456397,
  expires_at:new Date(Date.now()+2400000).toISOString(),
  repositories:['jtrtdhrst/harness-zar-i-szlif','jtrtdhrst/zar-i-szlif'],permissions});
 const write=v=>{writeFileSync(file,JSON.stringify(v),{mode:0o600});chmodSync(file,0o600)};
 const send=async(base)=>{
  const x=await fetch(base+'/mcp',{method:'POST',headers:{authorization:'Bearer role-test', 'content-type':'application/json'},
  body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'github_repo_info',arguments:{repo:REPO}}})});
  return (await x.json()).result;
 };
 let s=null;
 try{
  write(role('x'.repeat(50)));
  s=makeServer({callerToken:'role-test',githubToken:'',tokenFile:file,
   fetchImpl:async(url,opts)=>{seen.push(opts.headers.Authorization);return new Response(JSON.stringify({full_name:REPO,default_branch:'main'}),{status:200,headers:{'content-type':'application/json'}})}});
  await new Promise(r=>s.listen(0,'127.0.0.1',r));
  const base='http://127.0.0.1:'+s.address().port;
  assert.equal((await (await fetch(base+'/health')).json()).ready,true);
  assert.equal((await send(base)).structuredContent.full_name,REPO);
  write(role('y'.repeat(50)));
  assert.equal((await send(base)).structuredContent.full_name,REPO);
  assert.deepEqual(seen,['Bearer '+'x'.repeat(50),'Bearer '+'y'.repeat(50)]);
  write(role('z'.repeat(50),{actions:'write',administration:'read',contents:'read',deployments:'read',metadata:'read'}));
  assert.match((await send(base)).content[0].text,/AUTH_SCOPE_INVALID/);
  assert.equal((await (await fetch(base+'/health')).json()).ready,false);
  assert.equal(seen.length,2);
  write({...role('a'.repeat(50)),expires_at:new Date(Date.now()-60000).toISOString()});
  assert.match((await send(base)).content[0].text,/AUTH_FILE_EXPIRED/);
 }finally{if(s)await new Promise(r=>s.close(r));rmSync(dir,{recursive:true,force:true})}
});


test('GH Ops read-only reader cannot substitute for a separate writer',async()=>{
 const f=await fixture({writesEnabled:true,githubToken:'only-reader',writerToken:''});
 try {
   const out=await f.request('github_cancel_workflow_run',{repo:REPO,run_id:123,expected_sha:SHA});
   assert.equal(out.body.result.isError,true);
   assert.match(out.body.result.content[0].text,/WRITE_CREDENTIAL_MISSING/);
   assert.equal(f.calls.length,0,'no provider request without a writer grant');
 } finally { await f.close(); }
});
test('SHA-verified workflow cancellation uses separate writer token only for POST',async()=>{
 const f=await fixture({writesEnabled:true,githubToken:'reader-grant',writerToken:'writer-grant'});
 try {
   const out=await f.request('github_cancel_workflow_run',{repo:REPO,run_id:123,expected_sha:SHA});
   assert.equal(out.body.result.isError,undefined,JSON.stringify(out.body.result));
   assert.equal(out.body.result.structuredContent.cancel_requested,true);
   assert.deepEqual(f.calls.map(x=>x[0]),['GET','POST']);
   assert.deepEqual(f.authorizations,['Bearer reader-grant','Bearer writer-grant']);
 } finally { await f.close(); }
});
test('GitHub Ops reader role requires deployments read and refuses legacy four-scope grant',async()=>{
 const {mkdtempSync,writeFileSync,chmodSync,rmSync}=await import('node:fs');
 const {tmpdir}=await import('node:os'),{join}=await import('node:path');
 const dir=mkdtempSync(join(tmpdir(),'github-ops-scope-')),file=join(dir,'reader.json');
 let s=null;
 try{
   const role={role:'github-ops-reader',app_id:5398752,installation_id:173456397,
    token:'r'.repeat(50),expires_at:new Date(Date.now()+2400000).toISOString(),
    repositories:['jtrtdhrst/harness-zar-i-szlif','jtrtdhrst/zar-i-szlif'],
    permissions:{actions:'read',administration:'read',contents:'read',metadata:'read'}};
   writeFileSync(file,JSON.stringify(role),{mode:0o600});chmodSync(file,0o600);
   s=makeServer({callerToken:'bearer',githubToken:'',tokenFile:file});
   await new Promise(r=>s.listen(0,'127.0.0.1',r));
   const x=await fetch('http://127.0.0.1:'+s.address().port+'/health');
   assert.equal((await x.json()).github_configured,false);
 }finally{if(s)await new Promise(r=>s.close(r));rmSync(dir,{recursive:true,force:true})}
});

test('live MCP tools/list contains exact twenty names; removed dispatch is never advertised',async()=>{
 const f=await fixture();
 try {
   const tools=await toolsListed(f.root);
   const names=tools.map(t=>t.name).sort();
   assert.deepEqual(names,[
    'github_cancel_workflow_run','github_delete_merged_branch','github_get_actions_permissions',
    'github_get_branch_protection','github_get_deployments','github_get_rulesets',
    'github_preview_branch_delete','github_repo_info',
    'github_get_file','github_get_branch','github_list_branches','github_list_pull_requests',
    'github_get_pull_request','github_get_pr_files','github_get_check_runs','github_get_workflow_runs',
    'github_create_branch','github_commit_file','github_create_pull_request','github_merge_pull_request'].sort());
 }finally{await f.close()}
});
test('rotating GitHub App writer file governs only verified POST and fails closed',async()=>{
 const {mkdtempSync,writeFileSync,chmodSync,rmSync}=await import('node:fs');
 const {tmpdir}=await import('node:os'),{join}=await import('node:path');
 const dir=mkdtempSync(join(tmpdir(),'github-ops-writer-')),file=join(dir,'writer.json');
 const auths=[];
 const role=(token,permissions={actions:'write',contents:'write',pull_requests:'write',metadata:'read'})=>({
   token,role:'github-ops-writer',app_id:5398752,installation_id:173456397,
   expires_at:new Date(Date.now()+2400000).toISOString(),
   repositories:['jtrtdhrst/harness-zar-i-szlif','jtrtdhrst/zar-i-szlif'],permissions});
 const setRole=v=>{writeFileSync(file,JSON.stringify(v),{mode:0o600});chmodSync(file,0o600)};
 let s=null;
 try{
   setRole(role('w'.repeat(50)));
   s=makeServer({callerToken:'test-owner',githubToken:'reader-only',writerTokenFile:file,writesEnabled:true,
     fetchImpl:async(url,opts)=>{
      auths.push({method:opts.method,token:opts.headers.Authorization});
      const body=opts.method==='GET'?{head_sha:SHA,status:'in_progress',path:'.github/workflows/release-lanes-policy.yml'}:null;
      return new Response(body?JSON.stringify(body):null,{status:body?200:204,headers:{'content-type':'application/json'}});
     }});
   await new Promise(r=>s.listen(0,'127.0.0.1',r));
   const base='http://127.0.0.1:'+s.address().port;
   const cancel=async()=>{
    const x=await fetch(base+'/mcp',{method:'POST',headers:{authorization:'Bearer test-owner','content-type':'application/json'},
     body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'github_cancel_workflow_run',
      arguments:{repo:REPO,run_id:123,expected_sha:SHA}}})});
    return (await x.json()).result;
   };
   assert.equal((await (await fetch(base+'/health')).json()).writer_configured,true);
   assert.equal((await cancel()).structuredContent.cancel_requested,true);
   setRole(role('y'.repeat(50)));
   assert.equal((await cancel()).structuredContent.cancel_requested,true);
   assert.deepEqual(auths.map(x=>x.token),[
    'Bearer reader-only','Bearer '+'w'.repeat(50),'Bearer reader-only','Bearer '+'y'.repeat(50)]);
   setRole(role('z'.repeat(50),{actions:'read',contents:'write',metadata:'read'}));
   assert.equal((await (await fetch(base+'/health')).json()).writer_configured,false);
   assert.match((await cancel()).content[0].text,/AUTH_SCOPE_INVALID/);
   assert.equal(auths.filter(x=>x.method==='POST').length,2,'invalid grant never reaches GitHub mutation');
 }finally{if(s)await new Promise(r=>s.close(r));rmSync(dir,{recursive:true,force:true})}
});

test('single-repo rotating Harness reader enforces exact GitHub App scope and fail-closed rotation',async()=>{
 const {mkdtempSync,writeFileSync,chmodSync,rmSync}=await import('node:fs');
 const {tmpdir}=await import('node:os'),{join}=await import('node:path');
 const dir=mkdtempSync(join(tmpdir(),'github-ops-reader-harness-')),file=join(dir,'reader.json');
 const seen=[];
 const role=(token,overrides={})=>({
   token,role:'github-ops-reader-harness',app_id:5398752,installation_id:173456397,
   expires_at:new Date(Date.now()+2400000).toISOString(),
   repositories:[REPO],permissions:{contents:'read',metadata:'read'},...overrides
 });
 const write=v=>{writeFileSync(file,JSON.stringify(v),{mode:0o600});chmodSync(file,0o600)};
 let s=null;
 try {
   write(role('a'.repeat(50)));
   s=makeServer({callerToken:'narrow-reader-only',githubToken:'',tokenFile:file,
     tokenFileRole:'github-ops-reader-harness',writesEnabled:false,
     fetchImpl:async(url,opts)=>{
       seen.push(opts.headers.Authorization);
       return new Response(JSON.stringify({full_name:REPO,default_branch:'main'}),{status:200});
     }});
   await new Promise(r=>s.listen(0,'127.0.0.1',r));
   const base='http://127.0.0.1:'+s.address().port;
   const health=async()=> (await (await fetch(base+'/health')).json());
   const call=async()=> {
     const res=await fetch(base+'/mcp',{method:'POST',headers:{authorization:'Bearer narrow-reader-only'},
       body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',
         params:{name:'github_repo_info',arguments:{repo:REPO}}})});
     return (await res.json()).result;
   };
   assert.equal((await health()).ready,true);
   assert.equal((await health()).writes_enabled,false);
   assert.equal((await call()).structuredContent.full_name,REPO);
   const denied=await fetch(base+'/mcp',{method:'POST',headers:{authorization:'Bearer narrow-reader-only'},
     body:JSON.stringify({jsonrpc:'2.0',id:7,method:'tools/call',params:{name:'github_repo_info',
       arguments:{repo:'jtrtdhrst/zar-i-szlif'}}})});
   const blocked=(await denied.json()).result;
   assert.match(blocked.content[0].text,/REPO_DENIED/,'product access is rejected locally');
   assert.equal(seen.length,1,'product never reaches GitHub provider');
   write(role('b'.repeat(50)));
   assert.equal((await call()).structuredContent.full_name,REPO,'rotation without restart');
   assert.deepEqual(seen,['Bearer '+'a'.repeat(50),'Bearer '+'b'.repeat(50)]);
   for(const altered of [
     {repositories:[REPO,'jtrtdhrst/zar-i-szlif']},
     {repositories:['jtrtdhrst/zar-i-szlif']},
     {permissions:{contents:'write',metadata:'read'}},
     {permissions:{contents:'read'}},
     {permissions:{actions:'read',contents:'read',metadata:'read'}},
     {role:'github-ops-reader'},
     {expires_at:new Date(Date.now()+30000).toISOString()}
   ]){
     write(role('c'.repeat(50),altered));
     assert.equal((await health()).ready,false,'invalid scope must fail readiness');
     const out=await call();
     assert.equal(out.isError,true);
     assert.match(out.content[0].text,/AUTH_SCOPE_INVALID|AUTH_FILE_EXPIRED/);
     assert.equal(seen.length,2,'no GitHub provider call on invalid scope');
   }
   write(role('d'.repeat(50)));
   assert.equal((await call()).structuredContent.full_name,REPO,'recover after valid rotation');
 }finally{if(s)await new Promise(r=>s.close(r));rmSync(dir,{recursive:true,force:true})}
});

test('rotating reader role cannot be configured as writer or arbitrary credential role',()=>{
 for(const role of ['github-ops-writer','admin','github-ops-reader-harness-writer']){
   assert.throws(()=>makeServer({tokenFileRole:role,githubToken:''}),/Unsupported read-only GitHub App credential role/);
 }
 assert.throws(()=>makeServer({tokenFileRole:'github-ops-reader-harness',writesEnabled:true}),
   /Single-repository read-only role cannot enable writes/);
});

test('reader credential rejects symlink, multiple hard links, world-readable and non-root inode',async()=>{
 const {mkdtempSync,writeFileSync,chmodSync,chownSync,linkSync,symlinkSync,renameSync,unlinkSync,rmSync}=await import('node:fs');
 const {tmpdir}=await import('node:os'),{join}=await import('node:path');
 const dir=mkdtempSync(join(tmpdir(),'github-ops-file-hardening-')),file=join(dir,'token.json');
 const other=join(dir,'hard-link'),real=join(dir,'real.json');
 const payload={token:'a'.repeat(50),role:'github-ops-reader-harness',app_id:5398752,
   installation_id:173456397,expires_at:new Date(Date.now()+1800000).toISOString(),
   repositories:[REPO],permissions:{contents:'read',metadata:'read'}};
 writeFileSync(file,JSON.stringify(payload),{mode:0o600});
 let s=null,seen=0;
 try {
   s=makeServer({callerToken:'hardened-owner',tokenFile:file,
     tokenFileRole:'github-ops-reader-harness',githubToken:'',
     fetchImpl:async()=>{seen++;return new Response(JSON.stringify({full_name:REPO}),{status:200})}});
   await new Promise(r=>s.listen(0,'127.0.0.1',r));
   const base='http://127.0.0.1:'+s.address().port;
   const call=async()=> {
     const r=await fetch(base+'/mcp',{method:'POST',headers:{authorization:'Bearer hardened-owner'},
       body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',
         params:{name:'github_repo_info',arguments:{repo:REPO}}})});
     return (await r.json()).result;
   };
   assert.equal((await call()).structuredContent.full_name,REPO);
   chmodSync(file,0o644);
   assert.match((await call()).content[0].text,/AUTH_FILE_UNTRUSTED/);
   chmodSync(file,0o660);
   assert.match((await call()).content[0].text,/AUTH_FILE_UNTRUSTED/);
   chmodSync(file,0o600);
   linkSync(file,other);
   assert.match((await call()).content[0].text,/AUTH_FILE_UNTRUSTED/);
   unlinkSync(other);
   renameSync(file,real);symlinkSync(real,file);
   assert.match((await call()).content[0].text,/AUTH_FILE_UNTRUSTED/);
   unlinkSync(file);renameSync(real,file);
   if(process.getuid()===0){
     chownSync(file,1001,1001);
     assert.match((await call()).content[0].text,/AUTH_FILE_UNTRUSTED/);
     chownSync(file,0,0);
   }
   assert.equal((await call()).structuredContent.full_name,REPO,'valid inode restores service');
   assert.equal(seen,2,'no external calls for rejected token files');
 }finally{if(s)await new Promise(r=>s.close(r));rmSync(dir,{recursive:true,force:true})}
});

test('branch delete requires exact repository, branch and SHA grant before provider calls',async()=>{
  const f=await fixture({writesEnabled:true,pushToken:'test-push-token',approved:false});
  try {
    const x=await f.request('github_delete_merged_branch',{repo:REPO,branch:'fix/old',expected_sha:SHA});
    assert.match(x.body.result.content[0].text,/DELETE_NOT_APPROVED/);
    assert.equal(f.calls.length,0,'no provider request before operator grant');
  }finally{await f.close()}
});
test('preview checks GitHub branch rules and reports no deletion capability without a grant',async()=>{
  for(const opt of [
    {rulesList:[{id:123}],expected:'RULES_PRESENT'},
    {rulesStatus:403,rulesMessage:'Forbidden',expected:'RULES_UNAVAILABLE'},
    {rulesStatus:200,rulesList:[],approved:false,expected:null}
  ]){
    const f=await fixture(opt);
    try{
      const out=await f.request('github_preview_branch_delete',{repo:REPO,branch:'fix/old',expected_sha:SHA});
      if(opt.expected){
        assert.equal(out.body.result.isError,true);
        assert.match(out.body.result.content[0].text,new RegExp(opt.expected));
      }else{
        assert.equal(out.body.result.structuredContent.rules,'none');
        assert.equal(out.body.result.structuredContent.deletion_supported,false);
      }
      assert.equal(f.calls.some(([method])=>method!=='GET'),false,'preview never mutates provider');
    }finally{await f.close()}
  }
});

test('cached legacy MCP repo enums canonicalize to current GitHub owner, with no scope expansion',async()=>{
  const f=await fixture();
  try {
    for(const [oldName,newName] of [
      ['miloszspyrka-code/harness-zar-i-szlif','jtrtdhrst/harness-zar-i-szlif'],
      ['miloszspyrka-code/zar-i-szlif','jtrtdhrst/zar-i-szlif']
    ]){
      const x=await f.request('github_get_deployments',{repo:oldName,sha:SHA});
      assert.equal(x.http,200);
      assert.equal(x.body.result.structuredContent.repo,newName);
      assert.equal(x.body.result.structuredContent.count,0);
      assert.equal(f.calls.at(-1)[1],`/repos/${newName}/deployments?sha=${SHA}&per_page=30`);
    }
    const prior=f.calls.length;
    const denied=await f.request('github_repo_info',{repo:'someone/other'});
    assert.match(denied.body.result.content[0].text,/REPO_DENIED/);
    assert.equal(f.calls.length,prior);
  }finally{await f.close()}
});

test('classic protection 404 is informative and never overrides active rulesets',async()=>{
  const f=await fixture({classicProtectionMissing:true,rulesets:[{name:'main-protection',enforcement:'active'}]});
  try {
    const protection=await f.request('github_get_branch_protection',{repo:REPO});
    assert.equal(protection.http,200);
    assert.equal(protection.body.result.structuredContent.classic_protection,false);
    assert.equal(protection.body.result.structuredContent.ruleset_protection,'not_checked');
    const rules=await f.request('github_get_rulesets',{repo:REPO});
    assert.equal(rules.body.result.structuredContent.count,1);
    assert.equal(rules.body.result.structuredContent.rulesets[0].enforcement,'active');
  }finally{await f.close()}
});

test('poisoned HOME insteadOf cannot redirect a Git lease or receive writer credential', async () => {
  const {mkdirSync,writeFileSync} = await import('node:fs');
  const http = await import('node:http');
  const {join} = await import('node:path');
  const b = await bareWithBranch();
  const home=join(b.root,'poisoned-home');
  mkdirSync(home);
  let attackerRequests=0, attackerAuth=[];
  const attacker=http.createServer((req,res)=>{
    attackerRequests++;attackerAuth.push(req.headers.authorization??'');
    res.writeHead(401,{'WWW-Authenticate':'Basic realm="mock-attacker"'});res.end();
  });
  await new Promise(r=>attacker.listen(0,'127.0.0.1',r));
  const poison='[url "http://127.0.0.1:'+attacker.address().port+'/steal/"]\\n  insteadOf = '+b.url+'\\n';
  writeFileSync(join(home,'.gitconfig'),poison);
  const oldHome=process.env.HOME;
  try {
    process.env.HOME=home;
    const out=await deleteRefWithLease({remote:b.url,branch:b.branch,expectedSha:b.sha,pushToken:'synthetic-writer-secret'});
    assert.equal(out.accepted,true,JSON.stringify(out));
    assert.equal(b.ref(),null);
    assert.equal(attackerRequests,0,'Git must never read the poisoned global URL rewrite');
    assert.deepEqual(attackerAuth,[],'no request may include the writer credential');
  }finally{
    if(oldHome===undefined)delete process.env.HOME;else process.env.HOME=oldHome;
    await new Promise(r=>attacker.close(r));
    b.cleanup();
  }
});
