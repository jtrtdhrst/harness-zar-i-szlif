import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeServer, deleteRefWithLease, casDeleteArgs } from '../server.mjs';
const REPO='miloszspyrka-code/harness-zar-i-szlif', SHA='a'.repeat(40);
async function fixture({writesEnabled=false,allowDeletion=false, githubToken='x',callerToken='my-private-token',
  branchSHA=SHA,ahead=0,protectedBranch=false,approved=true,merged=true,openPR=false,mergeReachable=true,dispatchRunSHA=SHA,dispatchRunId=true,run404Count=0,
  deployments=[],rulesets=[],deploymentsInvalid=false,rulesetsInvalid=false,
  rulesStatus=200,rulesList=[],rulesMessage='Forbidden',pushToken='',pinnedBranches,pushRemoteFor,gitBin,liveRef=null,liveBranch='fix/old'}={}){
  const calls=[];
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
    const u=new URL(url);calls.push([opts.method,u.pathname+u.search]);
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
  const s=makeServer({fetchImpl:fake,githubToken,callerToken,writesEnabled,allowDeletion,
    pushToken,pinnedBranches,pushRemoteFor,gitBin,
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
test('tool metadata requires OAuth for all eight tools',async()=>{
 const f=await fixture();try{
  const response=await fetch(f.root+'/mcp',{method:'POST',headers:{authorization:'Bearer my-private-token'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'})});
  const tools=(await response.json()).result.tools;
  assert.equal(tools.length,8);
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
  for(const branch of ['ZARI-155','staging/github-ops','hold/release','operator

... [19459 characters truncated]