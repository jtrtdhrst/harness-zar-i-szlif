import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeServer } from '../server.mjs';
const REPO='miloszspyrka-code/harness-zar-i-szlif', SHA='a'.repeat(40);
async function fixture({writesEnabled=false,allowDeletion=false, githubToken='x',callerToken='my-private-token',
  branchSHA=SHA,ahead=0,protectedBranch=false,approved=true,merged=true,openPR=false,mergeReachable=true,dispatchRunSHA=SHA,dispatchRunId=true,run404Count=0}={}){
  const calls=[];
  let branchDeleted=false;
  let runReadsToMiss=run404Count;
  const mergeSHA='c'.repeat(40);
  const fake=async(url,opts)=>{
    const u=new URL(url);calls.push([opts.method,u.pathname+u.search]);
    let v={};
    if(opts.method==='DELETE'&&u.pathname.includes('/git/refs/heads/')){
      branchDeleted=true;
      return new Response(null,{status:204});
    }
    if(u.pathname.endsWith('/branches/main'))v={commit:{sha:SHA}};
    else if(u.pathname.includes('/branches/')){
      if(branchDeleted)return new Response(null,{status:404});
      v={commit:{sha:branchSHA},protected:protectedBranch};
    }
    else if(u.pathname.endsWith('/pulls')){
      if(u.searchParams.get('state')==='open')
        v=openPR?[{base:{ref:'fix/old'},head:{ref:'fix/old',repo:{full_name:REPO}}}]:[];
      else
        v=merged?[{number:987,merged_at:'2026-11-20T12:00:00Z',
          head:{ref:'fix/old',sha:SHA,repo:{full_name:REPO}},base:{ref:'main'},merge_commit_sha:mergeSHA}]:[];
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
    return new Response(opts.method==='POST'?null:JSON.stringify(v),{status:opts.method==='POST'?204:200,headers:{'content-type':'application/json'}});
  };
  const s=makeServer({fetchImpl:fake,githubToken,callerToken,writesEnabled,allowDeletion,
    deletionAllowlist:approved?[`${REPO}:fix/old@${SHA}`]:[],workflows:['release-lanes-policy.yml'],dispatchPollDelayMs:1});
  await new Promise(resolve=>s.listen(0,'127.0.0.1',resolve));
  const root=`http://127.0.0.1:${s.address().port}`;
  const request=async(name,args={},auth=true)=>{
    const x=await fetch(root+'/mcp',{method:'POST',headers:{'content-type':'application/json',...(auth?{authorization:`Bearer ${callerToken}`}:{})},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name,arguments:args}})});
    return {http:x.status,body:await x.json()};
  };
  return {s,root,calls,request,close:()=>new Promise(r=>s.close(r))};
}
test('real HTTP MCP initialize/list + no token denied',async()=>{
  const f=await fixture();try{
    const x=await f.request('github_repo_info',{repo:REPO},false);assert.equal(x.http,401);
    const y=await fetch(f.root+'/mcp',{method:'POST',headers:{authorization:'Bearer my-private-token'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'})});
    assert.equal((await y.json()).result.tools.length,8);
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
test('non-atomic deletion is not advertised and legacy call cannot write',async()=>{
 const f=await fixture({writesEnabled:true,allowDeletion:true});
 try{
  const list=await fetch(f.root+'/mcp',{method:'POST',headers:{authorization:'Bearer my-private-token'},
    body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'})});
  assert.equal((await list.json()).result.tools.some(t=>t.name==='github_delete_merged_branch'),false);
  const x=await f.request('github_delete_merged_branch',{repo:REPO,branch:'fix/old',expected_sha:SHA});
  assert.match(x.body.result.content[0].text,/TOOL_UNKNOWN/);
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
test('workflow dispatch returns only independently verified run ID and SHA',async()=>{
 const f=await fixture({writesEnabled:true});
 try{
  assert.match((await f.request('github_dispatch_workflow',{repo:REPO,workflow:'danger.yml',expected_sha:SHA})).body.result.content[0].text,/WORKFLOW_DENIED/);
  const out=await f.request('github_dispatch_workflow',{repo:REPO,workflow:'release-lanes-policy.yml',expected_sha:SHA});
  assert.equal(out.body.result.structuredContent.dispatched,true);
  assert.equal(out.body.result.structuredContent.verified,true);
  assert.equal(out.body.result.structuredContent.run_id,321);
  assert.equal(out.body.result.structuredContent.source_sha,SHA);
  assert.ok(f.calls.some(([method,path])=>method==='GET'&&path.endsWith('/actions/runs/321')));
 }finally{await f.close()}
});
test('main moves between SHA check and workflow dispatch: never claim success',async()=>{
 const f=await fixture({writesEnabled:true,dispatchRunSHA:'b'.repeat(40)});
 try{
  const out=await f.request('github_dispatch_workflow',{repo:REPO,workflow:'release-lanes-policy.yml',expected_sha:SHA});
  assert.match(out.body.result.content[0].text,/DISPATCH_SHA_MISMATCH/);
  assert.equal(out.body.result.structuredContent,undefined);
 }finally{await f.close()}
});
test('legacy 204 dispatch response is never claimed as verified; no blind retry',async()=>{
 const f=await fixture({writesEnabled:true,dispatchRunId:false});
 try{
  const out=await f.request('github_dispatch_workflow',{repo:REPO,workflow:'release-lanes-policy.yml',expected_sha:SHA});
  assert.match(out.body.result.content[0].text,/DISPATCH_UNVERIFIED/);
  assert.equal(f.calls.filter(([method,path])=>method==='POST'&&path.endsWith('/dispatches')).length,1);
 }finally{await f.close()}
});
test('accepted workflow dispatch retries transient run GET 404 without redispatch',async()=>{
 const f=await fixture({writesEnabled:true,run404Count:2});
 try{
  const x=await f.request('github_dispatch_workflow',{repo:REPO,workflow:'release-lanes-policy.yml',expected_sha:SHA});
  assert.equal(x.body.result.structuredContent.run_id,321);
  assert.equal(f.calls.filter(([method,path])=>method==='GET'&&path.endsWith('/actions/runs/321')).length,3);
  assert.equal(f.calls.filter(([method,path])=>method==='POST'&&path.endsWith('/dispatches')).length,1);
 }finally{await f.close()}
});
test('run remains unreadable: explicit ambiguous result, no second dispatch',async()=>{
 const f=await fixture({writesEnabled:true,run404Count:100});
 try{
  const x=await f.request('github_dispatch_workflow',{repo:REPO,workflow:'release-lanes-policy.yml',expected_sha:SHA});
  assert.match(x.body.result.content[0].text,/DISPATCH_UNVERIFIED/);
  assert.match(x.body.result.content[0].text,/321/);
  assert.equal(f.calls.filter(([method,path])=>method==='GET'&&path.endsWith('/actions/runs/321')).length,6);
  assert.equal(f.calls.filter(([method,path])=>method==='POST'&&path.endsWith('/dispatches')).length,1);
 }finally{await f.close()}
});
test('run cancellation exact SHA and allowlisted flow',async()=>{
 const f=await fixture({writesEnabled:true});try{
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
