import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeServer } from '../server.mjs';

const REPO='jtrtdhrst/harness-zar-i-szlif';
const SHA='a'.repeat(40),MERGE_SHA='b'.repeat(40),BLOB='c'.repeat(40);
const TREE='d'.repeat(40),NEW_BLOB='e'.repeat(40),NEW_TREE='f'.repeat(40),RACED='1'.repeat(40);
async function harness(config={}){
  const requests=[];
  let branchHead=SHA,prHead=SHA,prState='open';
  const fake=async(url,opts)=>{
    const u=new URL(url),method=opts.method,route=u.pathname;
    requests.push({method,route,search:u.search,auth:opts.headers.Authorization,body:opts.body?JSON.parse(opts.body):null});
    let status=200,v={};
    if(method==='GET'&&route.endsWith('/contents/src/example.txt')){
      v={type:'file',encoding:'base64',sha:BLOB,size:6,content:Buffer.from('hello\n').toString('base64')};
    }else if(method==='GET'&&route.endsWith('/branches/main'))
      v={name:'main',protected:true,commit:{sha:SHA}};
    else if(method==='GET'&&route.endsWith('/branches/feat/safe'))
      v={name:'feat/safe',protected:false,commit:{sha:branchHead}};
    else if(method==='GET'&&route.endsWith('/branches'))
      v=[{name:'main',protected:true,commit:{sha:SHA}}];
    else if(method==='GET'&&route.endsWith('/git/commits/'+SHA))
      v={sha:SHA,tree:{sha:TREE}};
    else if(method==='GET'&&route.endsWith('/pulls'))
      v=[];
    else if(method==='GET'&&route.endsWith('/pulls/42'))
      v={number:42,title:'safe PR',state:prState,head:{ref:'feat/safe',sha:prHead,repo:{full_name:REPO}},
        base:{ref:'main',sha:SHA},merged:false,merge_commit_sha:null,html_url:'https://github.com/jtrtdhrst/harness-zar-i-szlif/pull/42'};
    else if(method==='GET'&&route.endsWith('/pulls/42/files'))
      v=[{filename:'src/example.txt',patch:'@@ -1 +1 @@',status:'modified',additions:1,deletions:1}];
    else if(method==='GET'&&route.endsWith('/check-runs'))
      v={total_count:1,check_runs:[{name:'PR baseline',status:'completed',conclusion:'success'}]};
    else if(method==='GET'&&route.endsWith('/actions/runs'))
      v={total_count:1,workflow_runs:[{id:73,head_sha:SHA,name:'CI',status:'completed',conclusion:'success'}]};
    else if(method==='POST'&&route.endsWith('/git/refs')){status=201;v={ref:'refs/heads/feat/safe',object:{sha:SHA}};}
    else if(method==='POST'&&route.endsWith('/git/blobs')){status=201;v={sha:NEW_BLOB};}
    else if(method==='POST'&&route.endsWith('/git/trees')){status=201;v={sha:NEW_TREE};}
    else if(method==='POST'&&route.endsWith('/git/commits')){status=201;v={sha:MERGE_SHA};}
    else if(method==='PATCH'&&route.endsWith('/git/refs/heads/feat/safe')){
      if(config.simulateBranchRace){branchHead=RACED;status=422;v={message:'Update is not a fast forward'};}
      else {branchHead=MERGE_SHA;v={ref:'refs/heads/feat/safe',object:{sha:MERGE_SHA}};}
    }
    else if(method==='POST'&&route.endsWith('/pulls')){
      status=201;prHead=config.simulatePRRace?RACED:branchHead;
      v={number:42,head:{sha:prHead,ref:'feat/safe'},base:{ref:'main'},html_url:'https://github.com/jtrtdhrst/harness-zar-i-szlif/pull/42'};
    }
    else if(method==='PATCH'&&route.endsWith('/pulls/42')){prState='closed';v={number:42,state:prState};}
    else if(method==='PUT'&&route.endsWith('/pulls/42/merge')){status=200;v={merged:true,sha:MERGE_SHA};}
    else throw Error('Unexpected provider route '+method+' '+route+u.search);
    return new Response(JSON.stringify(v),{status,headers:{'content-type':'application/json'}});
  };
  const server=makeServer({callerToken:'test-auth',githubToken:'reader-grant',
    writerToken:'separate-writer-grant',mergeAllowlist:[REPO+':42@'+SHA],
    fetchImpl:fake,...config});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const uri='http://127.0.0.1:'+server.address().port+'/mcp';
  const call=async(name,params)=>{
    const r=await fetch(uri,{method:'POST',headers:{authorization:'Bearer test-auth','content-type':'application/json'},
      body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name,arguments:{repo:REPO,...params}}})});
    assert.equal(r.status,200);
    return (await r.json()).result;
  };
  const close=()=>new Promise(r=>server.close(r));
  return {call,requests,close,uri};
}
test('twenty live MCP tools have expected schemas and no legacy workflow dispatch',async()=>{
  const h=await harness();
  try{
    const r=await fetch(h.uri,{method:'POST',headers:{authorization:'Bearer test-auth','content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'})});
    const tools=(await r.json()).result.tools;
    assert.equal(tools.length,20);
    assert.equal(tools.some(t=>t.name==='github_dispatch_workflow'),false);
    const f=tools.find(t=>t.name==='github_commit_file');
    assert.deepEqual(f.inputSchema.required,['repo','branch','path','content','commit_message','expected_sha']);
    assert.equal(f.inputSchema.properties.blob_sha.pattern,'^[a-f0-9]{40}$');
  }finally{await h.close()}
});
test('eight new read-only actions return structured source, branch, PR and CI evidence',async()=>{
  const h=await harness();
  try{
    const calls=[
      ['github_get_file',{path:'src/example.txt'},x=>assert.equal(x.content,'hello\n')],
      ['github_get_branch',{branch:'main'},x=>assert.equal(x.sha,SHA)],
      ['github_list_branches',{},x=>assert.equal(x.branches[0].name,'main')],
      ['github_list_pull_requests',{},x=>assert.equal(x.count,0)],
      ['github_get_pull_request',{pr_number:42,expected_sha:SHA},x=>assert.equal(x.head_sha,SHA)],
      ['github_get_pr_files',{pr_number:42},x=>assert.equal(x.files[0].patch,'@@ -1 +1 @@')],
      ['github_get_check_runs',{sha:SHA},x=>assert.equal(x.checks[0].conclusion,'success')],
      ['github_get_workflow_runs',{sha:SHA},x=>assert.equal(x.runs[0].id,73)]
    ];
    for(const [name,args,verify] of calls){
      const result=await h.call(name,args);
      assert.equal(result.isError,undefined,name+': '+JSON.stringify(result));
      assert.ok(result.structuredContent && !Array.isArray(result.structuredContent),name);
      verify(result.structuredContent);
    }
    assert.equal(h.requests.every(x=>x.method==='GET'),true);
    const denied=await h.call('github_get_file',{path:'../.env'});
    assert.match(denied.content[0].text,/PATH_DENIED/);
  }finally{await h.close()}
});
test('all new write actions are unavailable before flag and writer credential checks',async()=>{
  const h=await harness({writesEnabled:false});
  try{
    for(const [name,args] of [
      ['github_create_branch',{branch:'feat/safe',expected_sha:SHA}],
      ['github_commit_file',{branch:'feat/safe',path:'src/example.txt',content:'ok',commit_message:'Update',expected_sha:SHA}],
      ['github_create_pull_request',{head:'feat/safe',expected_sha:SHA,title:'PR'}],
      ['github_merge_pull_request',{pr_number:42,expected_sha:SHA}]
    ]){
      const result=await h.call(name,args);
      assert.match(result.content[0].text,/WRITE_DISABLED/,name);
    }
    assert.equal(h.requests.length,0);
  }finally{await h.close()}
});
test('operator exact SHA, safe refs and grant checks reject writes before provider mutations',async()=>{
  const h=await harness({writesEnabled:true,mergeAllowlist:[]});
  try{
    const cases=[
      ['github_create_branch',{branch:'main',expected_sha:SHA},/BRANCH_DENIED/],
      ['github_create_branch',{branch:'feat/safe',expected_sha:MERGE_SHA},/STALE_SHA/],
      ['github_commit_file',{branch:'main',path:'src/example.txt',content:'ok',commit_message:'Update',expected_sha:SHA},/BRANCH_DENIED/],
      ['github_create_pull_request',{head:'feat/safe',base:'prod',expected_sha:SHA,title:'PR'},/BASE_DENIED/],
      ['github_merge_pull_request',{pr_number:42,expected_sha:SHA},/MERGE_NOT_APPROVED/]
    ];
    for(const [name,args,code] of cases)assert.match((await h.call(name,args)).content[0].text,code,name);
    assert.equal(h.requests.every(r=>r.method==='GET'),true);
  }finally{await h.close()}
});
test('approved operator flow writes immutable Git objects then advances only exact parent',async()=>{
  const h=await harness({writesEnabled:true});
  try{
    assert.equal((await h.call('github_create_branch',{branch:'feat/safe',expected_sha:SHA})).structuredContent.created,true);
    const committed=await h.call('github_commit_file',{branch:'feat/safe',path:'src/example.txt',
      content:'new content',commit_message:'feat: update example',expected_sha:SHA,blob_sha:BLOB});
    assert.equal(committed.structuredContent.commit_sha,MERGE_SHA);
    assert.equal(committed.structuredContent.blob_sha,NEW_BLOB);
    assert.equal((await h.call('github_create_pull_request',{head:'feat/safe',expected_sha:MERGE_SHA,title:'safe PR'})).structuredContent.number,42);
    const writes=h.requests.filter(r=>r.method!=='GET');
    assert.deepEqual(writes.map(x=>x.method),['POST','POST','POST','POST','PATCH','POST']);
    assert.equal(writes.every(x=>x.auth==='Bearer separate-writer-grant'),true);
    assert.equal(h.requests.filter(x=>x.method==='GET').every(x=>x.auth==='Bearer reader-grant'),true);
    const refUpdate=writes.find(x=>x.method==='PATCH'&&x.route.endsWith('/git/refs/heads/feat/safe'));
    assert.deepEqual(refUpdate.body,{sha:MERGE_SHA,force:false});
    const tree=writes.find(x=>x.route.endsWith('/git/trees'));
    assert.equal(tree.body.base_tree,TREE);
    const commit=writes.find(x=>x.route.endsWith('/git/commits'));
    assert.deepEqual(commit.body.parents,[SHA]);
  }finally{await h.close()}
});
test('concurrent branch movement rejects file commit without overwriting the changed ref',async()=>{
  const h=await harness({writesEnabled:true,simulateBranchRace:true});
  try{
    const result=await h.call('github_commit_file',{branch:'feat/safe',path:'src/example.txt',
      content:'new content',commit_message:'race rejection',expected_sha:SHA,blob_sha:BLOB});
    assert.match(result.content[0].text,/STALE_SHA/);
    assert.equal(h.requests.some(x=>x.method==='PUT'&&x.route.includes('/contents/')),false);
    const patch=h.requests.find(x=>x.method==='PATCH'&&x.route.endsWith('/git/refs/heads/feat/safe'));
    assert.equal(patch.body.force,false);
    const branch=await h.call('github_get_branch',{branch:'feat/safe'});
    assert.equal(branch.structuredContent.sha,RACED);
  }finally{await h.close()}
});
test('concurrent PR head movement is compensated by immediately closing the created PR',async()=>{
  const h=await harness({writesEnabled:true,simulatePRRace:true});
  try{
    const result=await h.call('github_create_pull_request',{head:'feat/safe',expected_sha:SHA,title:'safe PR'});
    assert.match(result.content[0].text,/STALE_SHA/);
    const writes=h.requests.filter(x=>x.method!=='GET');
    assert.deepEqual(writes.map(x=>x.method),['POST','PATCH']);
    assert.equal(writes[1].route.endsWith('/pulls/42'),true);
    assert.deepEqual(writes[1].body,{state:'closed'});
  }finally{await h.close()}
});
