import http from 'node:http';
import { timingSafeEqual } from 'node:crypto';

const REPOS = new Set(['miloszspyrka-code/harness-zar-i-szlif', 'miloszspyrka-code/zar-i-szlif']);
const SHA = /^[a-f0-9]{40}$/i;
const WORKFLOW = /^[a-zA-Z0-9][a-zA-Z0-9_.-]*\.ya?ml$/;
const TOOLS = [
  ['github_repo_info', 'Read current GitHub repository metadata', ['repo']],
  ['github_get_rulesets', 'Read rulesets; report GitHub plan/permission denials', ['repo']],
  ['github_get_actions_permissions', 'Read Actions permissions; report missing app permission', ['repo']],
  ['github_get_branch_protection', 'Read main branch protection; report missing administration permission', ['repo']],
  ['github_get_deployments', 'Read deployments for one exact source commit', ['repo', 'sha']],
  ['github_preview_branch_delete', 'Verify branch SHA, protection and merge status; no write', ['repo', 'branch', 'expected_sha']],
  ['github_delete_merged_branch', 'Delete a verified merged branch when deletion is explicitly enabled', ['repo', 'branch', 'expected_sha']],
  ['github_dispatch_workflow', 'Dispatch an allowlisted Actions workflow at verified main SHA', ['repo', 'workflow', 'expected_sha']],
  ['github_cancel_workflow_run', 'Cancel an allowlisted in-flight run at its verified SHA', ['repo', 'run_id', 'expected_sha']],
];
function secureEqual(a,b) {
  const aa=Buffer.from(a||''), bb=Buffer.from(b||'');
  return aa.length===bb.length && aa.length>0 && timingSafeEqual(aa,bb);
}
const error = (code,msg)=>Object.assign(new Error(msg),{code});
function assertRepo(repo){ if(!REPOS.has(repo))throw error('REPO_DENIED','Repository is not explicitly allowlisted');return repo; }
function assertSHA(sha){if(typeof sha!=='string'||!SHA.test(sha))throw error('SHA_INVALID','Exact 40-character SHA required');return sha;}
function assertBranch(branch){
  if(typeof branch!=='string'||!(/^[A-Za-z0-9][A-Za-z0-9._\/-]{0,120}$/).test(branch) || branch.includes('..') || branch.includes('//') || branch.endsWith('.lock') || /(^|\/)(main|master|ci-approved|release|production|prod)(\/|$)/i.test(branch))throw error('BRANCH_DENIED','Unsafe or protected branch name');
  return branch;
}
function githubClient({token,fetchImpl=fetch}){
  return async(method,path,body)=>{
    if(!token)throw error('AUTH_NOT_CONFIGURED','A scoped GitHub App or fine-grained credential is required');
    const result=await fetchImpl(`https://api.github.com${path}`,{method,headers:{Accept:'application/vnd.github+json',Authorization:`Bearer ${token}`,'X-GitHub-Api-Version':'2022-11-28','User-Agent':'github-ops-mcp/1.0',...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,redirect:'error'});
    if(!result.ok){throw error(`GITHUB_HTTP_${result.status}`,`GitHub API denied ${method} (${result.status})`);}
    if(result.status===204)return {accepted:true};
    return result.json();
  };
}
export function makeServer(config={}) {
  const callerToken=config.callerToken??process.env.GITHUB_OPS_CALLER_TOKEN??'';
  const githubToken=config.githubToken??process.env.GITHUB_TOKEN??'';
  const writesEnabled=config.writesEnabled??(process.env.GITHUB_OPS_WRITES_ENABLED==='true');
  const allowDeletion=config.allowDeletion??(process.env.GITHUB_OPS_BRANCH_DELETION==='true');
  const workflows=new Set(config.workflows??(process.env.GITHUB_OPS_WORKFLOWS??'release-lanes-policy.yml').split(',').map(x=>x.trim()));
  const api=githubClient({token:githubToken,fetchImpl:config.fetchImpl});
  async function execute(name,p={}){
    const repo=assertRepo(p.repo);
    const root=`/repos/${repo}`;
    if(name==='github_repo_info'){
      const r=await api('GET',root);return {full_name:r.full_name,default_branch:r.default_branch,permissions:r.permissions,allow_auto_merge:r.allow_auto_merge};
    }
    if(name==='github_get_rulesets')return api('GET',`${root}/rulesets`);
    if(name==='github_get_actions_permissions')return api('GET',`${root}/actions/permissions`);
    if(name==='github_get_branch_protection')return api('GET',`${root}/branches/main/protection`);
    if(name==='github_get_deployments')return api('GET',`${root}/deployments?sha=${assertSHA(p.sha)}&per_page=30`);
    if(name==='github_preview_branch_delete'||name==='github_delete_merged_branch'){
      const branch=assertBranch(p.branch),sha=assertSHA(p.expected_sha),q=branch.split('/').map(encodeURIComponent).join('/');
      const current=await api('GET',`${root}/branches/${q}`);
      if(current.commit?.sha!==sha)throw error('STALE_SHA','Branch moved: expected SHA does not match');
      if(current.protected)throw error('PROTECTED','GitHub reports branch protection');
      const cmp=await api('GET',`${root}/compare/main...${encodeURIComponent(branch)}`);
      if(cmp.ahead_by!==0)throw error('UNMERGED','Branch contains commits not reachable from main');
      if(name==='github_preview_branch_delete')return {safe:true,repo,branch,sha,ahead_by:0,note:'Deletion rechecks SHA, but GitHub DELETE ref has no atomic compare-and-delete lease'};
      if(!writesEnabled||!allowDeletion)throw error('WRITE_DISABLED','Writes and deletion must be independently authorized');
      // Recheck immediately before the non-atomic GitHub ref deletion.
      const fresh=await api('GET',`${root}/branches/${q}`);
      if(fresh.commit?.sha!==sha||fresh.protected)throw error('STALE_SHA','Branch changed before delete');
      await api('DELETE',`${root}/git/refs/heads/${q}`);
      return {deleted:true,repo,branch,sha};
    }
    if(name==='github_dispatch_workflow'){
      const sha=assertSHA(p.expected_sha),workflow=p.workflow;
      if(typeof workflow!=='string'||!WORKFLOW.test(workflow)||!workflows.has(workflow))throw error('WORKFLOW_DENIED','Workflow is not in the explicit allowlist');
      if(!writesEnabled)throw error('WRITE_DISABLED','GitHub writes disabled by default');
      const main=await api('GET',`${root}/branches/main`);
      if(main.commit?.sha!==sha)throw error('STALE_SHA','Main branch moved');
      await api('POST',`${root}/actions/workflows/${encodeURIComponent(workflow)}/dispatches`,{ref:'main'});
      return {dispatched:true,repo,workflow,source_sha:sha,verification:'Poll workflow runs by exact SHA before promoting'};
    }
    if(name==='github_cancel_workflow_run'){
      const sha=assertSHA(p.expected_sha),runid=p.run_id;
      if(!Number.isSafeInteger(runid)||runid<1)throw error('RUN_INVALID','Positive numeric run ID required');
      if(!writesEnabled)throw error('WRITE_DISABLED','GitHub writes disabled by default');
      const run=await api('GET',`${root}/actions/runs/${runid}`);
      if(run.head_sha!==sha)throw error('STALE_SHA','Run SHA moved');
      const workflowName=run.path?.split('/').pop();
      if(!workflows.has(workflowName))throw error('WORKFLOW_DENIED','Run workflow is not allowlisted');
      if(!['queued','in_progress','waiting','requested','pending'].includes(run.status))throw error('RUN_TERMINAL','Cannot cancel a terminal run');
      await api('POST',`${root}/actions/runs/${runid}/cancel`);
      return {cancel_requested:true,run_id:runid,head_sha:sha};
    }
    throw error('TOOL_UNKNOWN','Unknown tool');
  }
  const server=http.createServer(async(req,res)=>{
    const json=(status,obj)=>{res.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify(obj));};
    if(req.method==='GET'&&req.url==='/health')return json(200,{alive:true,ready:Boolean(callerToken&&githubToken),writes_enabled:Boolean(writesEnabled),github_configured:Boolean(githubToken)});
    if(req.url!=='/mcp'||req.method!=='POST')return json(404,{error:'not_found'});
    if(!callerToken||!secureEqual(req.headers.authorization?.replace(/^Bearer /,''),callerToken))return json(401,{error:'unauthorized'});
    try{
      let raw='';for await(const part of req){raw+=part;if(raw.length>65536)throw error('INPUT_LIMIT','Request exceeds size limit');}
      const v=JSON.parse(raw),id=v.id;
      if(v.jsonrpc!=='2.0'||typeof v.method!=='string')throw error('INVALID_REQUEST','Invalid JSON-RPC');
      if(v.method==='notifications/initialized')return json(202,{});
      if(v.method==='initialize')return json(200,{jsonrpc:'2.0',id,result:{protocolVersion:'2025-03-26',capabilities:{tools:{listChanged:false}},serverInfo:{name:'github-ops-mcp',version:'1.0.0'}}});
      if(v.method==='tools/list')return json(200,{jsonrpc:'2.0',id,result:{tools:TOOLS.map(([name,description,required])=>({name,description,inputSchema:{type:'object',properties:{repo:{type:'string',enum:[...REPOS]},branch:{type:'string'},expected_sha:{type:'string',pattern:SHA.source},workflow:{type:'string'},sha:{type:'string',pattern:SHA.source},run_id:{type:'integer'}},required,additionalProperties:false}}))}});
      if(v.method==='tools/call'){
        const name=v.params?.name;
        if(!TOOLS.some(x=>x[0]===name))throw error('TOOL_UNKNOWN','Tool not registered');
        const answer=await execute(name,v.params?.arguments??{});
        return json(200,{jsonrpc:'2.0',id,result:{content:[{type:'text',text:JSON.stringify(answer)}],structuredContent:answer}});
      }
      return json(200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Method not found'}});
    }catch(e){return json(200,{jsonrpc:'2.0',id:null,result:{isError:true,content:[{type:'text',text:JSON.stringify({code:e.code??'BAD_REQUEST',message:e.message??'Request failed'})}]}});}
  });
  return server;
}
if(process.argv[1]&&import.meta.url.endsWith(process.argv[1])){
  const port=Number(process.env.PORT??3000);
  makeServer().listen(port,'0.0.0.0',()=>console.log(`github-ops-mcp listening on port ${port}; credential values never logged`));
}
