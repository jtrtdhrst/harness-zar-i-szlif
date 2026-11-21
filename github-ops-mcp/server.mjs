import http from 'node:http';
import { readFile, lstat } from 'node:fs/promises';
import { timingSafeEqual, createPublicKey, verify as verifySignature } from 'node:crypto';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

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
  ['github_delete_merged_branch', 'Delete one merged-PR branch with a git protocol expected-SHA lease (CAS)', ['repo', 'branch', 'expected_sha']],
  ['github_cancel_workflow_run', 'Cancel an allowlisted in-flight run at its verified SHA', ['repo', 'run_id', 'expected_sha']],
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
  if (typeof remote !== 'string' || !/^(https:\/\/|file:\/\/\/)/.test(remote)) throw error('REMOTE_INVALID', 'Only literal https or file remotes are accepted');
  return ['push', '--porcelain', `--force-with-lease=refs/heads/${branch}:${expectedSha}`, remote, `:refs/heads/${branch}`];
}

// The token never enters argv (visible in /proc): git gets it through an
// environment variable read by an inline credential helper.
function gitEnv(pushToken) {
  return {
    PATH: process.env.PATH ?? '/usr/local/bin:/usr/bin:/bin',
    HOME: process.env.HOME ?? '/tmp',
    GIT_TERMINAL_PROMPT: '0',
    GIT_CONFIG_NOSYSTEM: '1',
    GIT_CONFIG_COUNT: '2',
    GIT_CONFIG_KEY_0: 'credential.helper',
    GIT_CONFIG_VALUE_0: '',
    GIT_CONFIG_KEY_1: 'credential.helper',
    GIT_CONFIG_VALUE_1: '!f() { echo "username=x-access-token"; echo "password=${GITHUB_OPS_PUSH_TOKEN}"; }; f',
    GITHUB_OPS_PUSH_TOKEN: pushToken,
  };
}

export async function deleteRefWithLease({ remote, branch, expectedSha, pushToken, gitBin = 'git', timeoutMs = 20000 }) {
  const args = casDeleteArgs({ remote, branch, expectedSha });
  const cwd = mkdtempSync(join(tmpdir(), 'ghops-'));
  const run = gitArgs => new Promise(resolve => {
    const child = spawn(gitBin, gitArgs, { cwd, env: gitEnv(pushToken), stdio: ['ignore', 'pipe', 'pipe'] });
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
function assertRepo(repo){ if(!REPOS.has(repo))throw error('REPO_DENIED','Repository is not explicitly allowlisted');return repo; }
function assertSHA(sha){if(typeof sha!=='string'||!SHA.test(sha))throw error('SHA_INVALID','Exact 40-character SHA required');return sha;}
function assertBranch(branch){
  if(typeof branch!=='string'||!(/^[A-Za-z0-9][A-Za-z0-9._\/-]{0,120}$/).test(branch) || branch.includes('..') || branch.includes('//') || branch.endsWith('.lock') || branch==='ZARI-155' || /(^|\/)(main|master|ci-approved|release|production|prod|hold|archive|staging|hotfix|deploy|operator)(\/|$)/i.test(branch))throw error('BRANCH_DENIED','Unsafe or protected branch name');
  return branch;
}
async function scopedTokenFromFile(path){
  try {
    const st=await lstat(path);
    if(!st.isFile() || st.isSymbolicLink() || st.uid!==0 || st.nlink!==1 || (st.mode & 0o007)!==0)
      throw error('AUTH_FILE_UNTRUSTED','GitHub credential file is not root-owned and private');
    const v=JSON.parse(await readFile(path,'utf8'));
    if(!v || typeof v.token!=='string' || v.token.length<40 || /\s/.test(v.token))
      throw error('AUTH_FILE_INVALID','GitHub installation token invalid');
    if(!v.expires_at || !Number.isFinite(Date.parse(v.expires_at)) || Date.parse(v.expires_at)<=Date.now()+120000)
      throw error('AUTH_FILE_EXPIRED','GitHub installation token expired');
    if(v.app_id!==5398752 || v.installation_id!==173456397 || v.role!=='github-ops-reader')
      throw error('AUTH_SCOPE_INVALID','GitHub installation token identity invalid');
    const expected=['miloszspyrka-code/harness-zar-i-szlif','miloszspyrka-code/zar-i-szlif'];
    if(!Array.isArray(v.repositories) || v.repositories.length!==2 || expected.some(r=>!v.repositories.includes(r)))
      throw error('AUTH_SCOPE_INVALID','GitHub installation repository scope invalid');
    const required={actions:'read',administration:'read',contents:'read',metadata:'read'};
    if(!v.permissions || Object.keys(v.permissions).length!==4 || Object.entries(required).some(([k,x])=>v.permissions[k]!==x))
      throw error('AUTH_SCOPE_INVALID','GitHub installation permission scope invalid');
    return v.token;
  } catch(e) {
    if(e.code?.startsWith('AUTH_'))throw e;
    throw error('AUTH_NOT_CONFIGURED','GitHub in

... [13357 characters truncated]