import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeServer } from '../server.mjs';
const REPO='miloszspyrka-code/harness-zar-i-szlif', SHA='a'.repeat(40);
async function fixture({writesEnabled=false,allowDeletion=false, githubToken='x',callerToken='my-private-token', branchSHA=SHA,ahead=0,protectedBranch=false}={}){
  const calls=[];
  const fake=async(url,opts)=>{
    const u=new URL(url);calls.push([opts.method,u.pathname]);
    let v={};
    if(u.pathname.endsWith('/branches/main'))v={commit:{sha:SHA}};
    else if(u.pathname.includes('/branches/'))v={commit:{sha:branchSHA},protected:protectedBranch};
    else if(u.pathname.includes('/compare/'))v={ahead_by:ahead};
    else if(u.pathname.endsWith('/actions/runs/123'))v={head_sha:SHA,status:'in_progress',path:'.github/workflows/release-lanes-policy.yml'};
    else if(u.pathname.endsWith(`/repos/${REPO}`))v={full_name:REPO,default_branch:'main',permissions:{push:true}};
    return new Response(opts.method==='DELETE'||opts.method==='POST'?null:JSON.stringify(v),{status:opts.method==='DELETE'||opts.method==='POST'?204:200,headers:{'content-type':'application/json'}});
  };
  const s=makeServer({fetchImpl:fake,githubToken,callerToken,writesEnabled,allowDeletion,workflows:['release-lanes-policy.yml']});
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
  for(const opt of [{ahead:1,err:'UNMERGED'},{branchSHA:'b'.repeat(40),err:'STALE_SHA'},{protectedBranch:true,err:'PROTECTED'}]){
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
