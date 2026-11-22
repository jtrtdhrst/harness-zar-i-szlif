import http from 'node:http';
import { readFile, lstat } from 'node:fs/promises';
import { timingSafeEqual, createPublicKey, verify as verifySignature } from 'node:crypto';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const REPOS = new Set(['jtrtdhrst/harness-zar-i-szlif', 'jtrtdhrst/zar-i-szlif']);
const SHA = /^[a-f0-9]{40}$/i;
const WORKFLOW = /^[a-zA-Z0-9][a-zA-Z0-9_.-]*\.ya?ml$/;
const TOOLS = [
  ['github_repo_info', 'Read current GitHub repository metadata', ['repo']],
  ['github_get_rulesets', 'Read rulesets; report GitHub plan/permission denials', ['repo']],
  ['github_get_actions_permissions', 'Read Actions permissions; report missing app permission', ['repo']],
  ['github_get_branch_protection', 'Read main branch protection; report missing administration permission', ['repo']],
  ['github_get_deployments', 'Read deployments for one exact source commit', ['repo', 'sha']],
  ['github_preview_branch_delete', 'Verify branch SHA, protection and merge status; no write', ['repo', 'branch', 'expected_sha']],
  ['github_delete_merged_branch', 'Delete one merged-PR branch with a git protocol expected-SHA lease (CAS)', ['repo', 'branch', 'expected_sha']],
  ['github_cancel_workflow_run', 'Cancel an allowlisted in-flight run at its verified SHA', ['repo', 'run_id', 'expected_sha']],
  ['github_get_file', 'Read exact repo source file and its Git blob SHA', ['repo', 'path']],
  ['github_get_branch', 'Read branch SHA and protection state', ['repo', 'branch']],
  ['github_list_branches', 'List first 100 branches with truncation signal', ['repo']],
  ['github_list_pull_requests', 'List first 50 PRs including current source SHA', ['repo']],
  ['github_get_pull_request', 'Read PR head/base SHAs and merge state', ['repo', 'pr_number']],
  ['github_get_pr_files', 'Read PR changed files and bounded diff patches', ['repo', 'pr_number']],
  ['github_get_check_runs', 'Read exact-SHA CI checks and conclusions', ['repo', 'sha']],
  ['github_get_workflow_runs', 'Read exact-SHA GitHub Actions runs', ['repo', 'sha']],
  ['github_create_branch', 'Create feature branch from verified current main SHA (write gate)', ['repo', 'branch', 'expected_sha']],
  ['github_commit_file', 'Commit one file to verified unprotected branch with blob CAS (write gate)', ['repo', 'branch', 'path', 'content', 'commit_message', 'expected_sha']],
  ['github_create_pull_request', 'Open PR against main from verified feature branch SHA (write gate)', ['repo', 'head', 'expected_sha', 'title']],
  ['github_merge_pull_request', 'Merge SHA-verified PR after exact operator grant and GitHub native rules (write gate)', ['repo', 'pr_number', 'expected_sha']],
];

// Branches a live Coolify application tracks. Deletion is refused for any of
// them even though the name passes assertBranch: the ref is a deployment pin,
// not a leftover. Keep in sync with ops/release-lanes.json.
const DEFAULT_PINNED_BRANCHES = ['feat/github-ops-mcp-20261120'];

// A branch delete that is atomic with respect to concurrent pushes. GitHub's
// REST DELETE /git/refs has no expected-SHA precondition, so a push landing
// between the read and the delete silently loses work. The git receive-pack
// protocol DOES take one: the delete command carries the old oid, and the
// server rejects it unless the ref still points there. `git push
// --force-with-lease=<ref>:<expect>` sends exactly that oid as the lease.
export function casDeleteArgs({ remote, branch, expectedSha }) {
  // Production pushes only to the literal GitHub origin; local file remotes
  // are permitted for isolated tests. Never rely on rewritten Git aliases.
  if (typeof remote !== 'string' || !(/^(https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\.git|file:\/\/\/.+)$/).test(remote))
    throw error('REMOTE_INVALID', 'Only canonical GitHub HTTPS or local test file remotes are accepted');
  return ['push', '--porcelain', `--force-with-lease=refs/heads/${branch}:${expectedSha}`, remote, `:refs/heads/${branch}`];
}

// The token never enters argv (visible in /proc): git gets it through an
// environment variable read by an inline credential helper.
function gitEnv(pushToken, isolatedHome, remote) {
  // All Git config inherited from the service account is untrusted: notably
  // url.*.insteadOf can silently rewrite github.com to a credential sink.
  const expectedPath=remote.startsWith('https://github.com/')
    ? new URL(remote).pathname.slice(1) : '';
  return {
    PATH: process.env.PATH ?? '/usr/local/bin:/usr/bin:/bin',
    HOME: isolatedHome,
    XDG_CONFIG_HOME: isolatedHome,
    GIT_CONFIG_NOSYSTEM: '1',
    GIT_CONFIG_GLOBAL: '/dev/null',
    GIT_TERMINAL_PROMPT: '0',
    GIT_CONFIG_COUNT: '3',
    GIT_CONFIG_KEY_0: 'credential.helper',
    GIT_CONFIG_VALUE_0: '',
    GIT_CONFIG_KEY_1: 'credential.useHttpPath',
    GIT_CONFIG_VALUE_1: 'true',
    GIT_CONFIG_KEY_2: 'credential.helper',
    // The helper is denied for any other host, protocol or repository path.
    GIT_CONFIG_VALUE_2: '!f() { protocol=; host=; path=; while IFS= read -r line; do case "$line" in protocol=*) protocol=${line#protocol=} ;; host=*) host=${line#host=} ;; path=*) path=${line#path=} ;; esac; done; [ "$protocol" = https ] && [ "$host" = github.com ] && [ "$path" = "$GITHUB_OPS_EXPECTED_PATH" ] || exit 1; printf "username=x-access-token\\npassword=%s\\n" "$GITHUB_OPS_PUSH_TOKEN"; }; f',
    GITHUB_OPS_EXPECTED_PATH: expectedPath,
    GITHUB_OPS_PUSH_TOKEN: pushToken,
  };
}
export async function deleteRefWithLease({ remote, branch, expectedSha, pushToken, gitBin = 'git', timeoutMs = 20000 }) {
  const args = casDeleteArgs({ remote, branch, expectedSha });
  const cwd = mkdtempSync(join(tmpdir(), 'ghops-'));
  const run = gitArgs => new Promise(resolve => {
    const child = spawn(gitBin, gitArgs, { cwd, env: gitEnv(pushToken, cwd, remote), stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', err = '', settled = false;
    const finish = value => { if (!settled) { settled = true; clearTimeout(timer); resolve(value); } };
    const timer = setTimeout(() => { try { child.kill('SIGKILL'); } catch {} finish({ code: -1, out, err: 'timeout' }); }, timeoutMs);
    child.stdout.on('data', chunk => { if (out.length < 4096) out += chunk; });
    child.stderr.on('data', chunk => { if (err.length < 4096) err += chunk; });
    child.on('error', () => finish({ code: -2, out, err: 'spawn_failed' }));
    child.on('close', code => finish({ code, out, err }));
  });
  try {
    // git refuses to push from outside any repository, so the throwaway
    // directory is initialised as an empty bare repository first.
    const init = await run(['init', '--bare', '-q', cwd]);
    if (init.code !== 0) return { accepted: false, code: 'GIT_INIT_FAILED' };
    const result = await run(args);
    if (result.code === 0) return { accepted: true };
    // git reports a refused lease as [rejected] ... (stale info) and never
    // sends a delete command, so the ref is untouched. --porcelain writes the
    // status line to stdout, so both streams are inspected.
    const combined = result.out + result.err;
    if (/stale info|\[rejected\]/i.test(combined)) return { accepted: false, code: 'STALE_LEASE_REJECTED' };
    return { accepted: false, code: result.code === -1 ? 'DELETE_TIMEOUT' : 'DELETE_FAILED', exit: result.code };
  } finally {
    try { rmSync(cwd, { recursive: true, force: true }); } catch {}
  }
}
function secureEqual(a,b) {
  const aa=Buffer.from(a||''), bb=Buffer.from(b||'');
  return aa.length===bb.length && aa.length>0 && timingSafeEqual(aa,bb);
}
const error = (code,msg)=>Object.assign(new Error(msg),{code});

 // Cloudflare verifies user identity at the edge, but the origin MUST verify
 // Cf-Access-Jwt-Assertion too: Docker peers can bypass the edge.
 // The JWKS URL is configured and never derived from untrusted JWT claims.
 function cloudflareJwtVerifier({ issuer, audience, ownerEmail, fetchImpl=fetch }) {
   if (!issuer || !audience || !ownerEmail) return async()=>false;
   const fixedIssuer=issuer.replace(/\/$/, '');
   if (!/^https:\/\/[a-z0-9-]+\.cloudflareaccess\.com$/i.test(fixedIssuer))
     throw error('ACCESS_CONFIG_INVALID','Access issuer must be a Cloudflare Access HTTPS team domain');
   let cache={keys:[],until:0};
   const decode=(part)=>JSON.parse(Buffer.from(part,'base64url').toString('utf8'));
   return async(token)=>{
     if(typeof token!=='string' || token.length>8192) return false;
     const parts=token.split('.');
     if(parts.length!==3) return false;
     try {
       const hdr=decode(parts[0]), body=decode(parts[1]);
       if(hdr.alg!=='RS256' || typeof hdr.kid!=='string' || hdr.kid.length>256) return false;
       const now=Math.floor(Date.now()/1000);
       if(body.iss!==fixedIssuer || !([body.aud].flat().includes(audience)) ||
          typeof body.exp!=='number' || body.exp<=now ||
          (typeof body.nbf==='number' && body.nbf>now) ||
          (typeof body.iat==='number' && body.iat>now+60) ||
          typeof body.email!=='string' || body.email.toLowerCase()!==ownerEmail.toLowerCase()) return false;
       let key=cache.until>Date.now()?cache.keys.find(k=>k.kid===hdr.kid):undefined;
       if(!key){
         const r=await fetchImpl(fixedIssuer+'/cdn-cgi/access/certs',{
           headers:{accept:'application/json'},redirect:'error',signal:AbortSignal.timeout(3000)
         });
         if(!r.ok) return false;
         const data=await r.json();
         if(!Array.isArray(data.keys) || data.keys.length>16) return false;
         const keys=data.keys.filter(k=>k.kty==='RSA' && k.alg==='RS256' &&
           k.use==='sig' && typeof k.kid==='string' && typeof k.n==='string' && typeof k.e==='string');
         cache={keys,until:Date.now()+300000};
         key=keys.find(k=>k.kid===hdr.kid);
       }
       if(!key)return false;
       return verifySignature('RSA-SHA256',Buffer.from(parts[0]+'.'+parts[1]),
         createPublicKey({key,format:'jwk'}),Buffer.from(parts[2],'base64url'));
     } catch { return false; }
   };
 }
// Compatibility for MCP clients whose cached enum still contains the previous owner.
// Resolve aliases BEFORE constructing the API path; authorization still applies only
// to the two current repositories in REPOS and the current scoped GitHub App grant.
const LEGACY_REPO_ALIASES = new Map([
  ['miloszspyrka-code/harness-zar-i-szlif', 'jtrtdhrst/harness-zar-i-szlif'],
  ['miloszspyrka-code/zar-i-szlif', 'jtrtdhrst/zar-i-szlif'],
]);
function assertRepo(repo){
  const canonical = LEGACY_REPO_ALIASES.get(repo) ?? repo;
  if(!REPOS.has(canonical))throw error('REPO_DENIED','Repository is not explicitly allowlisted');
  return canonical;
}
function assertFilePath(path){
  if(typeof path!=='string' || !/^[A-Za-z0-9._-][A-Za-z0-9._\/-]{0,239}$/.test(path) ||
     path.includes('..') || path.includes('//') || path.endsWith('/') ||
     path.split('/').some(s=>s==='.' || s==='..')) throw error('PATH_DENIED','Unsafe repository file path');
  return path;
}
function assertPRNumber(n){
  if(!Number.isSafeInteger(n) || n<=0)throw error('PR_INVALID','Positive PR number required');
  return n;
}
function assertReadRef(ref){
  if(ref===undefined || ref===null || ref==='')return 'main';
  if(ref==='main')return ref;
  return assertBranch(ref);
}
function assertMessage(value,field,limit){
  if(typeof value!=='string' || !value.trim() || value.length>limit || [...value].some(c=>c.charCodeAt(0)<32 && ![9,10,13].includes(c.charCodeAt(0))))
    throw error('TEXT_INVALID',field+' must be nonempty bounded text');
  return value;
}
function assertSHA(sha){if(typeof sha!=='string'||!SHA.test(sha))throw error('SHA_INVALID','Exact 40-character SHA required');return sha;}
function assertBranch(branch){
  if(typeof branch!=='string'||!(/^[A-Za-z0-9][A-Za-z0-9._\/-]{0,120}$/).test(branch) || branch.includes('..') || branch.includes('//') || branch.endsWith('.lock') || branch==='ZARI-155' || /(^|\/)(main|master|ci-approved|release|production|prod|hold|archive|staging|hotfix|deploy|operator)(\/|$)/i.test(branch))throw error('BRANCH_DENIED','Unsafe or protected branch name');
  return branch;
}
async function scopedTokenFromFile(path, expectedRole='github-ops-reader'){
  try {
    const st=await lstat(path);
    if(!st.isFile() || st.isSymbolicLink() || st.uid!==0 || st.nlink!==1 || (st.mode & 0o007)!==0)
      throw error('AUTH_FILE_UNTRUSTED','GitHub credential file is not root-owned and private');
    const v=JSON.parse(await readFile(path,'utf8'));
    if(!v || typeof v.token!=='string' || v.token.length<40 || /\s/.test(v.token))
      throw error('AUTH_FILE_INVALID','GitHub installation token invalid');
    if(!v.expires_at || !Number.isFinite(Date.parse(v.expires_at)) || Date.parse(v.expires_at)<=Date.now()+120000)
      throw error('AUTH_FILE_EXPIRED','GitHub installation token expired');
    if(v.app_id!==5398752 || v.installation_id!==173456397 || v.role!==expectedRole)
      throw error('AUTH_SCOPE_INVALID','GitHub installation token identity invalid');
    const expected=['jtrtdhrst/harness-zar-i-szlif','jtrtdhrst/zar-i-szlif'];
    if(!Array.isArray(v.repositories) || v.repositories.length!==2 || expected.some(r=>!v.repositories.includes(r)))
      throw error('AUTH_SCOPE_INVALID','GitHub installation repository scope invalid');
    const allowedPermissions={
      'github-ops-reader':{actions:'read',administration:'read',contents:'read',deployments:'read',metadata:'read'},
      'github-ops-writer':{actions:'write',contents:'write',pull_requests:'write',metadata:'read'},
    };
    const required=allowedPermissions[expectedRole];
    if(!required || !v.permissions || Object.keys(v.permissions).length!==Object.keys(required).length || Object.entries(required).some(([k,x])=>v.permissions[k]!==x))
      throw error('AUTH_SCOPE_INVALID','GitHub installation permission scope invalid');
    return v.token;
  } catch(e) {
    if(e.code?.startsWith('AUTH_'))throw e;
    throw error('AUTH_NOT_CONFIGURED','GitHub installation credential file unavailable');
  }
}
function githubClient({token,getToken,fetchImpl=fetch}){
  return async(method,path,body)=>{
    const resolvedToken=getToken?await getToken():token;
    if(!resolvedToken)throw error('AUTH_NOT_CONFIGURED','A scoped GitHub App or fine-grained credential is required');
    const result=await fetchImpl(`https://api.github.com${path}`,{method,headers:{Accept:'application/vnd.github+json',Authorization:`Bearer ${resolvedToken}`,'X-GitHub-Api-Version':'2026-03-10','User-Agent':'github-ops-mcp/1.0',...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,redirect:'error'});
    if(!result.ok){
      let detail='';
      try{ detail=(await result.text()).slice(0,512); }catch{}
      const denied=error(`GITHUB_HTTP_${result.status}`,`GitHub API denied ${method} (${result.status})`);
      denied.status=result.status;
      denied.detail=detail;
      throw denied;
    }
    if(result.status===204)return {accepted:true};
    return result.json();
  };
}
export function makeServer(config={}) {
  const callerToken=config.callerToken??process.env.GITHUB_OPS_CALLER_TOKEN??'';
  const githubToken=config.githubToken??process.env.GITHUB_TOKEN??'';
  const tokenFile=config.tokenFile??process.env.GITHUB_OPS_TOKEN_FILE??'';
  const writerTokenFile=config.writerTokenFile??process.env.GITHUB_OPS_WRITER_TOKEN_FILE??'';
  const writesEnabled=config.writesEnabled??(process.env.GITHUB_OPS_WRITES_ENABLED==='true');
  // Only explicit in-process test injection may use a static token. Production
  // mutating calls resolve the short-lived GitHub App writer grant from a file.
  const injectedPushToken=config.pushToken??'';
  const injectedWriterToken=config.writerToken??'';
  const pinnedBranches=new Set(config.pinnedBranches??(process.env.GITHUB_OPS_PINNED_BRANCHES??DEFAULT_PINNED_BRANCHES.join(',')).split(',').map(x=>x.trim()).filter(Boolean));
  const deletionAllowlist=new Set(config.deletionAllowlist??(process.env.GITHUB_OPS_DELETION_ALLOWLIST??'').split(',').map(x=>x.trim()).filter(Boolean));
  const pushRemoteFor=config.pushRemoteFor??(repo=>`https://github.com/${repo}.git`);
  const gitBin=config.gitBin??'git';
  const workflows=new Set(config.workflows??(process.env.GITHUB_OPS_WORKFLOWS??'release-lanes-policy.yml').split(',').map(x=>x.trim()));
  const mergeAllowlist=new Set(config.mergeAllowlist??(process.env.GITHUB_OPS_MERGE_ALLOWLIST??'').split(',').map(x=>x.trim()).filter(Boolean));
  const ensureWrite=()=>{
    if(!writesEnabled)throw error('WRITE_DISABLED','GitHub writes disabled by default');
    if(!writerTokenFile&&!injectedWriterToken)throw error('WRITE_CREDENTIAL_MISSING','Separate rotating writer grant required');
  };
  const ensureBranchWritable=branch=>{
    const b=assertBranch(branch);
    if(pinnedBranches.has(b))throw error('BRANCH_PINNED','Deployed branch is read-only');
    return b;
  };
  const api=githubClient({token:githubToken,getToken:tokenFile?()=>scopedTokenFromFile(tokenFile):null,fetchImpl:config.fetchImpl});
  const readWriterToken=async()=>{
    if(writerTokenFile)return scopedTokenFromFile(writerTokenFile,'github-ops-writer');
    if(injectedWriterToken)return injectedWriterToken;
    if(injectedPushToken)return injectedPushToken;
    throw error('WRITE_CREDENTIAL_MISSING','A dedicated short-lived GitHub App writer credential is required');
  };
  const writerApi=githubClient({token:injectedWriterToken||injectedPushToken,getToken:readWriterToken,fetchImpl:config.fetchImpl});
  const access=cloudflareJwtVerifier({
    issuer:config.accessIssuer??process.env.CF_ACCESS_ISSUER??'',
    audience:config.accessAudience??process.env.CF_ACCESS_AUD??'',
    ownerEmail:config.accessOwnerEmail??process.env.CF_ACCESS_OWNER_EMAIL??'',
    fetchImpl:config.accessFetchImpl
  });
  const branchQ=branch=>branch.split('/').map(encodeURIComponent).join('/');
  const listPulls=async(root,state)=>{
    const items=[];
    for(let page=1;page<=20;page++){
      const batch=await api('GET',`${root}/pulls?state=${state}&per_page=100&page=${page}`);
      if(!Array.isArray(batch))throw error('PR_LIST_INVALID','GitHub pull request listing returned invalid data');
      items.push(...batch);
      if(batch.length<100)return items;
    }
    throw error('PR_PAGE_LIMIT','Cannot verify all GitHub pull requests');
  };
  const openHasRef=(items,branch,repo)=>items.some(pr=>pr.base?.ref===branch||(pr.head?.ref===branch&&pr.head?.repo?.full_name===repo));
  // Shared by preview and delete: exact SHA, unprotected, no open PR, and a
  // merged PR whose head SHA is exactly this branch head.
  async function branchDeleteEvidence(repo,root,branch,sha){
    const current=await api('GET',`${root}/branches/${branchQ(branch)}`);
    if(current.commit?.sha?.toLowerCase()!==sha)throw error('STALE_SHA','Branch moved');
    if(current.protected)throw error('PROTECTED','GitHub reports branch protection');
    if(openHasRef(await listPulls(root,'open'),branch,repo))throw error('OPEN_PR','An open pull request uses this branch');
    const merged=(await listPulls(root,'closed')).find(pr=>pr.merged_at&&pr.base?.ref==='main'
      &&pr.head?.ref===branch&&pr.head?.sha?.toLowerCase()===sha
      &&pr.head?.repo?.full_name===repo&&SHA.test(pr.merge_commit_sha||''));
    if(!merged)throw error('MERGE_NOT_VERIFIED','No matching merged PR with this exact branch SHA');
    const cmp=await api('GET',`${root}/compare/${merged.merge_commit_sha}...main`);
    if(cmp.behind_by!==0)throw error('MERGE_NOT_REACHABLE','Merged PR commit not on current main');
    return {current,merged};
  }
  // GitHub reports 403 for the rules endpoint on app/plan limitations. A scope
  // denial or a 5xx means protection state is unknown, so deletion stops. The
  // one exception is GitHub saying outright that this repository cannot have
  // rulesets (private repository without GitHub Pro): then no rule of that kind
  // can exist, and classic protection is still enforced through the branch's
  // own `protected` flag, which is checked before this point.
  async function assertNoRules(repo,root,branch){
    let rules;
    try{ rules=await api('GET',`${root}/rules/branches/${branchQ(branch)}`); }
    catch(e){
      const planLimited=e.status===403&&/upgrade to github pro|make this repository public/i.test(e.detail||'');
      if(!planLimited)throw error('RULES_UNAVAILABLE',`Cannot verify repository rules (${e.code??'unknown'}); refusing to delete`);
      return {rules:'unavailable_on_plan',count:0};
    }
    if(!Array.isArray(rules))throw error('RULES_UNAVAILABLE','Repository rules reply is not a list');
    if(rules.length)throw error('RULES_PRESENT','Repository rules apply to this branch');
    return {rules:'none',count:rules.length};
  }
  async function execute(name,p={}){
    const repo=assertRepo(p.repo);
    const root=`/repos/${repo}`;
    if(name==='github_repo_info'){
      const r=await api('GET',root);return {full_name:r.full_name,default_branch:r.default_branch,permissions:r.permissions,allow_auto_merge:r.allow_auto_merge};
    }
    if(name==='github_get_rulesets'){
      const list=await api('GET',`${root}/rulesets`);
      if(!Array.isArray(list))throw error('RULESETS_INVALID','GitHub ruleset listing returned invalid data');
      return {repo,rulesets:list,count:list.length};
    }
    if(name==='github_get_actions_permissions')return api('GET',`${root}/actions/permissions`);
    if(name==='github_get_branch_protection'){
      try{return await api('GET',`${root}/branches/main/protection`);}
      catch(e){
        // 404 means no CLASSIC branch protection; an active repository ruleset
        // can still protect main. Never represent this as an unprotected branch.
        if(e.code==='GITHUB_HTTP_404')return {repo,classic_protection:false,
          ruleset_protection:'not_checked',
          note:'No classic branch protection endpoint; check github_get_rulesets before changing refs'};
        throw e;
      }
    }
    if(name==='github_get_deployments'){
      const sha=assertSHA(p.sha).toLowerCase();
      const list=await api('GET',`${root}/deployments?sha=${sha}&per_page=30`);
      if(!Array.isArray(list))throw error('DEPLOYMENTS_INVALID','GitHub deployment listing returned invalid data');
      return {repo,sha,count:list.length,deployments:list};
    }

    if(name==='github_get_file'){
      const path=assertFilePath(p.path);
      const branch=assertReadRef(p.branch);
      const item=await api('GET',`${root}/contents/${path.split('/').map(encodeURIComponent).join('/')}?ref=${encodeURIComponent(branch)}`);
      if(item.type!=='file' || typeof item.content!=='string' || item.encoding!=='base64' || !SHA.test(item.sha||''))
        throw error('FILE_INVALID','GitHub returned no supported text file');
      if(item.size>131072)throw error('FILE_TOO_LARGE','Only text files <=128 KiB are supported');
      const raw=Buffer.from(item.content.replace(/\\s/g,''),'base64');
      if(raw.includes(0) || raw.toString('utf8').includes('\uFFFD'))throw error('FILE_BINARY','Binary files are not returned as text');
      return {repo,path,branch,sha:item.sha,size:item.size,content:raw.toString('utf8')};
    }
    if(name==='github_get_branch'){
      const branch=assertReadRef(p.branch);
      const b=await api('GET',`${root}/branches/${branchQ(branch)}`);
      return {repo,branch,sha:b.commit?.sha,protected:Boolean(b.protected)};
    }
    if(name==='github_list_branches'){
      const rows=await api('GET',`${root}/branches?per_page=100`);
      if(!Array.isArray(rows))throw error('BRANCHES_INVALID','GitHub branch list invalid');
      return {repo,count:rows.length,truncated:rows.length===100,
        branches:rows.map(b=>({name:b.name,sha:b.commit?.sha,protected:Boolean(b.protected)}))};
    }
    if(name==='github_list_pull_requests'){
      const state=p.state??'open';
      if(!['open','closed','all'].includes(state))throw error('STATE_INVALID','PR state invalid');
      const rows=await api('GET',`${root}/pulls?state=${state}&per_page=50`);
      if(!Array.isArray(rows))throw error('PR_LIST_INVALID','GitHub PR list invalid');
      return {repo,state,count:rows.length,truncated:rows.length===50,
        pull_requests:rows.map(pr=>({number:pr.number,title:pr.title,state:pr.state,draft:Boolean(pr.draft),
          head:pr.head?.ref,head_sha:pr.head?.sha,base:pr.base?.ref,merged:Boolean(pr.merged_at),url:pr.html_url}))};
    }
    if(name==='github_get_pull_request'){
      const number=assertPRNumber(p.pr_number);
      const pr=await api('GET',`${root}/pulls/${number}`);
      if(p.expected_sha && pr.head?.sha?.toLowerCase()!==assertSHA(p.expected_sha).toLowerCase())
        throw error('STALE_SHA','PR head changed');
      return {repo,number,title:pr.title,body:pr.body??'',state:pr.state,draft:Boolean(pr.draft),
        head:pr.head?.ref,head_sha:pr.head?.sha,base:pr.base?.ref,base_sha:pr.base?.sha,
        mergeable:pr.mergeable,mergeable_state:pr.mergeable_state,merged:Boolean(pr.merged),
        merge_commit_sha:pr.merge_commit_sha,url:pr.html_url};
    }
    if(name==='github_get_pr_files'){
      const number=assertPRNumber(p.pr_number);
      const list=await api('GET',`${root}/pulls/${number}/files?per_page=100`);
      if(!Array.isArray(list))throw error('PR_FILES_INVALID','GitHub PR files invalid');
      return {repo,number,count:list.length,truncated:list.length===100,
        files:list.map(f=>({path:f.filename,status:f.status,additions:f.additions,deletions:f.deletions,
          blob_sha:f.sha,patch:typeof f.patch==='string'?f.patch.slice(0,5000):null}))};
    }
    if(name==='github_get_check_runs'){
      const sha=assertSHA(p.sha).toLowerCase();
      const response=await api('GET',`${root}/commits/${sha}/check-runs?per_page=100`);
      if(!Array.isArray(response.check_runs))throw error('CHECKS_INVALID','GitHub checks invalid');
      return {repo,sha,count:response.total_count,truncated:response.total_count>response.check_runs.length,
        checks:response.check_runs.map(x=>({name:x.name,status:x.status,conclusion:x.conclusion,
          app:x.app?.slug,url:x.details_url}))};
    }
    if(name==='github_get_workflow_runs'){
      const sha=assertSHA(p.sha).toLowerCase();
      const response=await api('GET',`${root}/actions/runs?head_sha=${sha}&per_page=30`);
      if(!Array.isArray(response.workflow_runs))throw error('RUNS_INVALID','GitHub runs invalid');
      return {repo,sha,count:response.total_count,truncated:response.total_count>response.workflow_runs.length,
        runs:response.workflow_runs.map(x=>({id:x.id,name:x.name,head_sha:x.head_sha,status:x.status,
          conclusion:x.conclusion,url:x.html_url,run_attempt:x.run_attempt}))};
    }
    if(name==='github_create_branch'){
      const branch=ensureBranchWritable(p.branch),sha=assertSHA(p.expected_sha).toLowerCase();
      ensureWrite();
      const main=await api('GET',`${root}/branches/main`);
      if(main.commit?.sha?.toLowerCase()!==sha)throw error('STALE_SHA','Main moved before branch creation');
      await writerApi('POST',`${root}/git/refs`,{ref:`refs/heads/${branch}`,sha});
      const current=await api('GET',`${root}/branches/${branchQ(branch)}`);
      if(current.commit?.sha?.toLowerCase()!==sha)throw error('READBACK_MISMATCH','Created ref does not match exact SHA');
      return {created:true,repo,branch,sha};
    }
    if(name==='github_commit_file'){
      const branch=ensureBranchWritable(p.branch),path=assertFilePath(p.path);
      const sha=assertSHA(p.expected_sha).toLowerCase();
      const content=assertMessage(p.content,'content',131072);
      const message=assertMessage(p.commit_message,'commit_message',256);
      ensureWrite();
      const prior=await api('GET',`${root}/branches/${branchQ(branch)}`);
      if(prior.commit?.sha?.toLowerCase()!==sha)throw error('STALE_SHA','Branch moved before file commit');
      if(prior.protected)throw error('PROTECTED','Protected branch is not writable');
      // Resolve file and base tree at an immutable commit, never at a moving branch.
      const base=await api('GET',`${root}/git/commits/${sha}`);
      if(!SHA.test(base.tree?.sha||''))throw error('BASE_TREE_INVALID','Commit has no valid tree');
      let existing=null;
      try{existing=await api('GET',`${root}/contents/${path.split('/').map(encodeURIComponent).join('/')}?ref=${sha}`);}
      catch(e){if(e.code!=='GITHUB_HTTP_404')throw e;}
      if(existing && (existing.type!=='file'||!SHA.test(existing.sha||'')))throw error('FILE_INVALID','Existing target is not a regular file');
      if(existing && (!p.blob_sha||assertSHA(p.blob_sha).toLowerCase()!==existing.sha.toLowerCase()))
        throw error('BLOB_SHA_REQUIRED','Exact current blob SHA required to update an existing file');
      if(!existing && p.blob_sha)throw error('FILE_CHANGED','Expected blob is missing');
      // Git object creation does not move any ref; only the final non-force
      // fast-forward succeeds if the branch still equals our exact parent.
      const blob=await writerApi('POST',`${root}/git/blobs`,{content,encoding:'utf-8'});
      if(!SHA.test(blob.sha||''))throw error('BLOB_CREATE_INVALID','GitHub returned no blob SHA');
      const tree=await writerApi('POST',`${root}/git/trees`,{
        base_tree:base.tree.sha,tree:[{path,mode:'100644',type:'blob',sha:blob.sha}]
      });
      if(!SHA.test(tree.sha||''))throw error('TREE_CREATE_INVALID','GitHub returned no tree SHA');
      const commit=await writerApi('POST',`${root}/git/commits`,{message,tree:tree.sha,parents:[sha]});
      if(!SHA.test(commit.sha||''))throw error('COMMIT_CREATE_INVALID','GitHub returned no commit SHA');
      try{
        await writerApi('PATCH',`${root}/git/refs/heads/${branchQ(branch)}`,{sha:commit.sha,force:false});
      }catch(e){
        if(e.code==='GITHUB_HTTP_422'||e.code==='GITHUB_HTTP_409')
          throw error('STALE_SHA','Non-fast-forward update rejected; branch moved concurrently');
        throw e;
      }
      const readback=await api('GET',`${root}/branches/${branchQ(branch)}`);
      if(readback.commit?.sha?.toLowerCase()!==commit.sha.toLowerCase())
        throw error('BRANCH_MOVED_AFTER_COMMIT','Branch advanced after this commit; refresh before next write');
      return {committed:true,repo,branch,path,commit_sha:commit.sha,blob_sha:blob.sha,created:!existing};
    }
    if(name==='github_create_pull_request'){
      const head=ensureBranchWritable(p.head),sha=assertSHA(p.expected_sha).toLowerCase();
      if((p.base??'main')!=='main')throw error('BASE_DENIED','Only PRs into main supported');
      const title=assertMessage(p.title,'title',200);
      const body=p.body??'';
      if(typeof body!=='string'||body.length>30000)throw error('TEXT_INVALID','PR body too long');
      ensureWrite();
      const b=await api('GET',`${root}/branches/${branchQ(head)}`);
      if(b.commit?.sha?.toLowerCase()!==sha)throw error('STALE_SHA','PR head branch moved');
      if((await listPulls(root,'open')).some(pr=>pr.head?.ref===head&&pr.head?.repo?.full_name===repo&&pr.base?.ref==='main'))
        throw error('PR_EXISTS','Existing open PR for this branch; reuse it');
      // GitHub PR creation binds to a branch name, not an immutable SHA. Validate
      // the new PR by readback and compensate by closing it if a race is found.
      const created=await writerApi('POST',`${root}/pulls`,{title,head,base:'main',body,draft:false});
      if(!Number.isSafeInteger(created.number)||created.number<1)
        throw error('PR_CREATE_INVALID','GitHub did not return an identifiable PR');
      let observed=null;
      try{observed=await api('GET',`${root}/pulls/${created.number}`);}catch{}
      const matches=created.head?.sha?.toLowerCase()===sha&&
        observed?.head?.sha?.toLowerCase()===sha&&observed?.head?.ref===head&&
        observed?.base?.ref==='main'&&observed?.state==='open';
      if(!matches){
        try{await writerApi('PATCH',`${root}/pulls/${created.number}`,{state:'closed'});}
        catch{throw error('PR_ROLLBACK_FAILED',`PR ${created.number} could not be verified or closed; manual intervention required`);}
        throw error('STALE_SHA','PR head changed during creation or readback failed; created PR closed');
      }
      return {created:true,repo,number:created.number,head,head_sha:sha,base:'main',url:created.html_url};
    }
    if(name==='github_merge_pull_request'){
      const number=assertPRNumber(p.pr_number),sha=assertSHA(p.expected_sha).toLowerCase();
      const method=p.merge_method??'squash';
      if(!['squash','merge','rebase'].includes(method))throw error('MERGE_METHOD_INVALID','Unsupported merge method');
      ensureWrite();
      if(!mergeAllowlist.has(`${repo}:${number}@${sha}`))throw error('MERGE_NOT_APPROVED','Exact PR and SHA must be operator-authorized');
      const pr=await api('GET',`${root}/pulls/${number}`);
      if(pr.state!=='open'||pr.base?.ref!=='main'||pr.head?.sha?.toLowerCase()!==sha)
        throw error('STALE_SHA','PR missing or current head/base has moved');
      const result=await writerApi('PUT',`${root}/pulls/${number}/merge`,{sha,merge_method:method});
      if(result.merged!==true||!SHA.test(result.sha||''))throw error('MERGE_UNCONFIRMED','GitHub did not confirm merge');
      const readback=await api('GET',`${root}/pulls/${number}`);
      if(!readback.merged||readback.merge_commit_sha?.toLowerCase()!==result.sha.toLowerCase())
        throw error('MERGE_READBACK_MISMATCH','Merged PR readback does not match GitHub merge result');
      return {merged:true,repo,number,head_sha:sha,merge_sha:result.sha,method};
    }
    if(name==='github_preview_branch_delete'){
      const branch=assertBranch(p.branch),sha=assertSHA(p.expected_sha).toLowerCase();
      const {merged}=await branchDeleteEvidence(repo,root,branch,sha);
      const rules=await assertNoRules(repo,root,branch);
      return {eligible:true,repo,branch,sha,merged_pr:merged.number,rules:rules.rules,
        deletion_supported:Boolean(writesEnabled&&(writerTokenFile||injectedPushToken)&&deletionAllowlist.has(`${repo}:${branch}@${sha}`)),
        note:'Deletion is available only through github_delete_merged_branch, which deletes with a git --force-with-lease=<ref>:<expected> lease: a concurrent push is rejected (stale lease), never overwritten'};
    }
    if(name==='github_delete_merged_branch'){
      const branch=assertBranch(p.branch),sha=assertSHA(p.expected_sha).toLowerCase();
      // Fail closed before any provider or git traffic.
      if(!writesEnabled)throw error('WRITE_DISABLED','GitHub writes disabled by default');
      if(!writerTokenFile&&!injectedPushToken)throw error('PUSH_CREDENTIAL_MISSING','A repo-scoped writer credential is required for CAS deletion');
      if(pinnedBranches.has(branch))throw error('BRANCH_PINNED','A live deployment tracks this branch; deletion refused');
      if(!deletionAllowlist.has(`${repo}:${branch}@${sha}`))throw error('DELETE_NOT_APPROVED','Exact repo:branch@sha operator grant required');
      const {merged}=await branchDeleteEvidence(repo,root,branch,sha);
      const rules=await assertNoRules(repo,root,branch);
      const pushToken=await readWriterToken();
      const lease=await deleteRefWithLease({remote:pushRemoteFor(repo),branch,expectedSha:sha,pushToken,gitBin});
      if(!lease.accepted)throw error(lease.code,`CAS delete refused (${lease.code}); the ref was not removed`);
      let stillThere=true;
      try{ await api('GET',`${root}/branches/${branchQ(branch)}`); }
      catch(e){ if(e.code==='GITHUB_HTTP_404')stillThere=false; else throw error('READBACK_UNAVAILABLE',`Deletion readback failed (${e.code??'unknown'})`); }
      if(stillThere)throw error('DELETE_NOT_CONFIRMED','Branch is still readable after a CAS delete');
      return {deleted:true,repo,branch,sha,merged_pr:merged.number,lease:'force-with-lease',rules:rules.rules,readback:'404'};
    }
    // Disabled: workflow_dispatch with ref:main cannot atomically bind the requested SHA.
    if(name==='github_cancel_workflow_run'){
      const sha=assertSHA(p.expected_sha),runid=p.run_id;
      if(!Number.isSafeInteger(runid)||runid<1)throw error('RUN_INVALID','Positive numeric run ID required');
      if(!writesEnabled)throw error('WRITE_DISABLED','GitHub writes disabled by default');
      if(!writerTokenFile&&!injectedWriterToken)throw error('WRITE_CREDENTIAL_MISSING','A scoped writer credential is required for cancelling runs');
      const run=await api('GET',`${root}/actions/runs/${runid}`);
      if(run.head_sha!==sha)throw error('STALE_SHA','Run SHA moved');
      const workflowName=run.path?.split('/').pop();
      if(!workflows.has(workflowName))throw error('WORKFLOW_DENIED','Run workflow is not allowlisted');
      if(!['queued','in_progress','waiting','requested','pending'].includes(run.status))throw error('RUN_TERMINAL','Cannot cancel a terminal run');
      await writerApi('POST',`${root}/actions/runs/${runid}/cancel`);
      return {cancel_requested:true,run_id:runid,head_sha:sha};
    }
    throw error('TOOL_UNKNOWN','Unknown tool');
  }
  const resourceUrl=config.resourceUrl??process.env.GITHUB_OPS_RESOURCE_URL??'https://github-ops-mcp.zariszlif.pl/mcp';
  const resourceMetadata=resourceUrl.replace(/\/mcp$/,'')+'/.well-known/oauth-protected-resource/mcp';
  const authChallenge='Bearer resource_metadata="'+resourceMetadata+'", error="invalid_token", error_description="Authenticate with Cloudflare Access OAuth"';
  const server=http.createServer(async(req,res)=>{
    const json=(status,obj)=>{res.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify(obj));};
    if(req.method==='GET'&&req.url==='/health'){
      const configured=tokenFile?await scopedTokenFromFile(tokenFile).then(()=>true,()=>false):Boolean(githubToken);
      const writerConfigured=writerTokenFile?await scopedTokenFromFile(writerTokenFile,'github-ops-writer').then(()=>true,()=>false):false;
      return json(200,{alive:true,ready:Boolean(callerToken&&configured),writes_enabled:Boolean(writesEnabled),github_configured:configured,writer_configured:writerConfigured});
    }
    if(req.url==='/mcp'&&req.method==='GET'){res.writeHead(405,{'allow':'POST','cache-control':'no-store'});return res.end();}
    if(req.url!=='/mcp'||req.method!=='POST')return json(404,{error:'not_found'});
    const bearer=req.headers.authorization?.match(/^Bearer (.+)$/)?.[1]??'';
    const bearerAuthorized=Boolean(callerToken&&secureEqual(bearer,callerToken));
    const accessAuthorized=bearerAuthorized?false:await access(req.headers['cf-access-jwt-assertion']);
    if(!bearerAuthorized&&!accessAuthorized){
      res.writeHead(401,{'content-type':'application/json','cache-control':'no-store','www-authenticate':authChallenge});
      return res.end(JSON.stringify({error:'invalid_token',error_description:'OAuth authentication required'}));
    }
    let messageId=null;
    try{
      let raw='';for await(const part of req){raw+=part;if(raw.length>65536)throw error('INPUT_LIMIT','Request exceeds size limit');}
      const v=JSON.parse(raw),id=v.id;messageId=id??null;
      if(v.jsonrpc!=='2.0'||typeof v.method!=='string')throw error('INVALID_REQUEST','Invalid JSON-RPC');
      if(v.method==='notifications/initialized')return json(202,{});
      if(v.method==='initialize')return json(200,{jsonrpc:'2.0',id,result:{protocolVersion:'2025-03-26',capabilities:{tools:{listChanged:false}},serverInfo:{name:'github-ops-mcp',version:'1.2.0'}}});
      if(v.method==='tools/list')return json(200,{jsonrpc:'2.0',id,result:{tools:TOOLS.map(([name,description,required])=>({name,description,securitySchemes:[{type:'oauth2',scopes:[]}],_meta:{securitySchemes:[{type:'oauth2',scopes:[]}]},inputSchema:{type:'object',properties:{repo:{type:'string',enum:[...REPOS]},branch:{type:'string'},expected_sha:{type:'string',pattern:SHA.source},sha:{type:'string',pattern:SHA.source},run_id:{type:'integer'},path:{type:'string'},content:{type:'string'},blob_sha:{type:'string',pattern:SHA.source},commit_message:{type:'string'},head:{type:'string'},base:{type:'string'},title:{type:'string'},body:{type:'string'},state:{type:'string',enum:['open','closed','all']},pr_number:{type:'integer'},merge_method:{type:'string',enum:['squash','merge','rebase']}},required,additionalProperties:false}}))}});
      if(v.method==='tools/call'){
        const name=v.params?.name;
        if(!TOOLS.some(x=>x[0]===name))
          throw error('TOOL_UNKNOWN','Tool not registered; removed tools stay disabled. Re-initialize the client tool list to reconcile a stale tool cache');
        const answer=await execute(name,v.params?.arguments??{});
        // MCP requires structuredContent to be an object. A bare array (an empty GitHub list) is invalid.
        const structured=answer&&typeof answer==='object'&&!Array.isArray(answer)?answer:{result:answer??null};
        return json(200,{jsonrpc:'2.0',id,result:{content:[{type:'text',text:JSON.stringify(structured)}],structuredContent:structured}});
      }
      return json(200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Method not found'}});
    }catch(e){return json(200,{jsonrpc:'2.0',id:messageId,result:{isError:true,content:[{type:'text',text:JSON.stringify({code:e.code??'BAD_REQUEST',message:e.message??'Request failed'})}]}});}
  });
  return server;
}
if(process.argv[1]&&import.meta.url.endsWith(process.argv[1])){
  const port=Number(process.env.PORT??3000);
  makeServer().listen(port,'0.0.0.0',()=>console.log(`github-ops-mcp listening on port ${port}; credential values never logged`));
}

