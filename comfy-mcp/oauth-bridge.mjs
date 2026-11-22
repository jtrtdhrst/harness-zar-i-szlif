import http from 'node:http';
import { createPublicKey, verify as verifySignature } from 'node:crypto';

const port = Number(process.env.LISTEN_PORT || 9101);
const upstream = new URL(process.env.MCP_UPSTREAM || 'http://comfy-mcp:9100');
const accessIssuer = process.env.CF_ACCESS_ISSUER;
const accessAudience = process.env.CF_ACCESS_AUD;
const originToken = process.env.COMFYUI_MCP_HTTP_TOKEN;
const jwksUrl = process.env.CF_ACCESS_JWKS_URL || `${accessIssuer}/cdn-cgi/access/certs`;
if (!accessIssuer || !accessAudience || !originToken || !upstream.hostname || upstream.protocol !== 'http:') {
  throw new Error('Missing/invalid access policy, upstream, or origin credentials');
}

let jwks = { at: 0, keys: [] };
function bad(message) { const e = new Error(message); e.name = 'AuthorizationError'; throw e; }
function decode(segment) { return JSON.parse(Buffer.from(segment, 'base64url').toString('utf8')); }
async function verifyAccessToken(token) {
  if (!token || typeof token !== 'string' || token.length > 16_384) bad('missing or invalid Access JWT');
  const parts = token.split('.');
  if (parts.length !== 3) bad('invalid Access JWT shape');
  let header, payload;
  try { header = decode(parts[0]); payload = decode(parts[1]); }
  catch { bad('malformed Access JWT'); }
  if (header.alg !== 'RS256' || !header.kid || !payload) bad('unsupported Access JWT');
  const now = Math.floor(Date.now()/1000);
  if (payload.iss !== accessIssuer || !(Array.isArray(payload.aud) ? payload.aud : [payload.aud]).includes(accessAudience)) bad('Access JWT issuer/audience mismatch');
  if (typeof payload.exp !== 'number' || payload.exp < now || (typeof payload.nbf === 'number' && payload.nbf > now+30)) bad('expired/not-yet-valid Access JWT');
  if (!payload.sub && !payload.email) bad('missing Access JWT principal');
  if (!jwks.keys.length || Date.now()-jwks.at > 300_000) {
    const response = await fetch(jwksUrl, { signal: AbortSignal.timeout(10_000) });
    if (!response.ok) throw new Error(`JWKS unavailable (${response.status})`);
    const body = await response.json();
    jwks = {at: Date.now(), keys: (body.keys || []).filter(x => x.kty === 'RSA' && x.kid)};
  }
  let key = jwks.keys.find(x => x.kid === header.kid);
  if (!key) {
    jwks.at = 0;
    const response = await fetch(jwksUrl, { signal: AbortSignal.timeout(10_000) });
    if (!response.ok) throw new Error('JWKS refresh unavailable');
    const body = await response.json();
    jwks = {at: Date.now(), keys: (body.keys || []).filter(x => x.kty === 'RSA' && x.kid)};
    key = jwks.keys.find(x => x.kid === header.kid);
  }
  if (!key) bad('unrecognized Access JWT key id');
  try {
    if (!verifySignature('RSA-SHA256', Buffer.from(parts[0]+'.'+parts[1]), createPublicKey({key,format:'jwk'}), Buffer.from(parts[2], 'base64url'))) bad('invalid Access JWT signature');
  } catch(e) { if(e.name === 'AuthorizationError') throw e; bad('invalid Access JWT key or signature'); }
  return payload;
}

const hopHeaders = new Set(['host','authorization','x-api-key','cf-access-jwt-assertion','connection','proxy-connection','keep-alive','upgrade','te','trailer','transfer-encoding','proxy-authenticate','proxy-authorization']);
const server = http.createServer(async (req,res) => {
  const path = new URL(req.url || '/', 'http://localhost').pathname;
  if (path === '/healthz') { res.writeHead(200,{'Content-Type':'text/plain'}); res.end('ok'); return; }
  if (path !== '/mcp' || !['GET','POST','DELETE'].includes(req.method)) {res.writeHead(404);res.end();return;}
  if (Number(req.headers['content-length'] || 0) > 48*1024*1024) {res.writeHead(413);res.end();return;}
  let identity;
  try { identity = await verifyAccessToken(req.headers['cf-access-jwt-assertion']); }
  catch(e) {
    const code = e.name === 'AuthorizationError' ? 401 : 503;
    res.writeHead(code, {'Content-Type':'application/json', 'Cache-Control':'no-store'});
    res.end(JSON.stringify({error:code === 401?'unauthorized':'verification_unavailable'}));
    return;
  }
  const headers = {};
  for (const [key,value] of Object.entries(req.headers)) if (!hopHeaders.has(key)) headers[key] = value;
  headers.authorization = 'Bearer '+originToken;
  headers.host = upstream.host;
  const upstreamReq = http.request({hostname:upstream.hostname,port:upstream.port || 80,path:req.url,method:req.method,headers,timeout:900_000},upstreamRes=>{
    const responseHeaders = {};
    for(const [key,value] of Object.entries(upstreamRes.headers)) if (!hopHeaders.has(key)) responseHeaders[key]=value;
    res.writeHead(upstreamRes.statusCode ?? 502, responseHeaders);
    upstreamRes.pipe(res);
  });
  upstreamReq.on('timeout',()=>upstreamReq.destroy(new Error('upstream timeout')));
  upstreamReq.on('error',()=>{if(!res.headersSent){res.writeHead(502);res.end('upstream unavailable');}else res.destroy();});
  req.on('aborted',()=>upstreamReq.destroy());
  req.pipe(upstreamReq);
});
server.listen(port,'0.0.0.0',()=>console.log(JSON.stringify({event:'ready',port,upstream:upstream.host,jwksOrigin:new URL(jwksUrl).origin})));
