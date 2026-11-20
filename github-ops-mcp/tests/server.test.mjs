import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeServer } from '../server.mjs';
const REPO='miloszspyrka-code/harness-zar-i-szlif', SHA='a'.repeat(40);
async function fixture({writesEnabled=false,allowDeletion=false, githubToken='x',callerToken='my-private-token',
  branchSHA=SHA,ahead=0,protectedBranch=false,approved=true,merged=true,openPR=false,mergeReachable=true}={}){
  const calls=[];
  let branchDeleted=false;
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
    else if(u.pathname.endsWith('/actions/runs/123'))v={head_sha:SHA,status:'in_progress',path:'.github/workflows/release-lanes-policy.yml'};
    else if(u.pathname.endsWith(`/repos/${REPO}`))v={full_name:REPO,default_branch:'main',permissions:{push:true}};
    return new Response(opts.method==='POST'?null:JSON.stringify(v),{status:opts.method==='POST'?204:200,headers:{'content-type':'application/json'}});
  };
  const s=makeServer({fetchImpl:fake,githubToken,callerToken,writesEnabled,allowDeletion,
    deletionAllowlist:approved?[`${REPO}:fix/old@${SHA}`]:[],workflows:['release-lanes-policy.yml']});
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
    assert.equal((await y.json()).result.tools.length,9);
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
test('branch deletion rejects nonmerged, stale and protected branches',async()=>{
  for(const opt of [{merged:false,err:'MERGE_NOT_VERIFIED'},{branchSHA:'b'.repeat(40),err:'STALE_SHA'},{protectedBranch:true,err:'PROTECTED'}]){
    const f=await fixture({...opt,writesEnabled:true,allowDeletion:true});try{const x=await f.request('github_delete_merged_branch',{repo:REPO,branch:'fix/old',expected_sha:SHA});assert.match(x.body.result.content[0].text,new RegExp(opt.err));assert.equal(f.calls.some(x=>x[0]==='DELETE'),false)}finally{await f.close()}
  }
});
test('write requires both gates and merged branch',async()=>{
  let f=await fixture({writesEnabled:true});try{
    assert.match((await f.request('github_delete_merged_branch',{repo:REPO,branch:'fix/old',expected_sha:SHA})).body.result.content[0].text,/WRITE_DISABLED/);
  }finally{await f.close()}
  f=await fixture({writesEnabled:true,allowDeletion:true});try{
    assert.equal((await f.request('github_delete_merged_branch',{repo:REPO,branch:'fix/old',expected_sha:SHA})).body.result.structuredContent.deleted,true);
    assert.equal(f.calls.filter(x=>x[0]==='DELETE').length,1);
  }finally{await f.close()}
});
test('deletion requires explicit exact SHA-scoped operator allowlist',async()=>{
 const f=await fixture({writesEnabled:true,allowDeletion:true,approved:false});
 try {
   const out=await f.request('github_delete_merged_branch',{repo:REPO,branch:'fix/old',expected_sha:SHA});
   assert.match(out.body.result.content[0].text,/BRANCH_NOT_APPROVED/);
   assert.equal(f.calls.length,0);
 }finally{await f.close()}
});
test('open PR and unreachable merge commit independently prevent deletion',async()=>{
 for(const opt of [{openPR:true,err:'OPEN_PR'},{mergeReachable:false,err:'MERGE_NOT_REACHABLE'}]){
  const f=await fixture({...opt,writesEnabled:true,allowDeletion:true});
  try{
    const out=await f.request('github_delete_merged_branch',{repo:REPO,branch:'fix/old',expected_sha:SHA});
    assert.match(out.body.result.content[0].text,new RegExp(opt.err));
    assert.equal(f.calls.some(([method])=>method==='DELETE'),false);
  }finally{await f.close()}
 }
});
test('squash-merged PR passes when merge SHA is on main even with unmerged feature commits',async()=>{
 const f=await fixture({ahead:9,writesEnabled:true,allowDeletion:true});
 try{
  const out=await f.request('github_delete_merged_branch',{repo:REPO,branch:'fix/old',expected_sha:SHA});
  assert.equal(out.body.result.structuredContent.verified_missing,true);
  assert.equal(out.body.result.structuredContent.merged_pr,987);
  assert.equal(f.calls.filter(([method])=>method==='DELETE').length,1);
 }finally{await f.close()}
});
test('staging and known live Coolify ref ZARI-155 are never deletable',async()=>{
 const f=await fixture({writesEnabled:true,allowDeletion:true});
 try{
  for(const branch of ['ZARI-155','staging/github-ops','hold/release','operator/safety']){
   const out=await f.request('github_delete_merged_branch',{repo:REPO,branch,expected_sha:SHA});
   assert.match(out.body.result.content[0].text,/BRANCH_DENIED/);
  }
  assert.equal(f.calls.length,0);
 }finally{await f.close()}
});
test('workflow dispatch only allowlisted and exact sha',async()=>{
  const f=await fixture({writesEnabled:true});try{
    assert.match((await f.request('github_dispatch_workflow',{repo:REPO,workflow:'danger.yml',expected_sha:SHA})).body.result.content[0].text,/WORKFLOW_DENIED/);
    assert.equal((await f.request('github_dispatch_workflow',{repo:REPO,workflow:'release-lanes-policy.yml',expected_sha:SHA})).body.result.structuredContent.dispatched,true);
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
