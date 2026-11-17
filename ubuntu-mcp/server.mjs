// ubuntu-mcp-bridge: private authenticated Streamable HTTP MCP -> mcp-ssh-manager stdio.
// Paperclip Tool Gateway -> POST /mcp (Bearer) -> stdio child -> SSH -> Ubuntu.
// URL clients -> POST /mcp?key=<url-key> (query, for clients that cannot set headers).
// ChatGPT custom MCP -> OAuth 2.1 discovery + PKCE; /authorize asks for the URL
// key once, so a human approves each connection and no token is stored by ChatGPT.
// No secrets in code/logs. Audit JSONL with redaction. Stateless HTTP (multi-session safe).
import { createServer } from "node:http";
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { spawn } from "node:child_process";
import { readFileSync, appendFileSync } from "node:fs";

const PORT = Number(process.env.BRIDGE_PORT || "8765");
const TOKEN_FILE = process.env.BRIDGE_TOKEN_FILE || "/bridge-config/bridge-bearer-token";
const CHILD_CMD = process.env.BRIDGE_CHILD_CMD || "node";
const CHILD_ARGS = (process.env.BRIDGE_CHILD_ARGS || "/opt/mcp-ssh-manager/src/index.js").split(" ").filter(Boolean);
const AUDIT_FILE = process.env.BRIDGE_AUDIT_FILE || "/audit/ubuntu-mcp-audit.jsonl";
// mcp-ssh-manager caps ssh_execute at 300s; keep the bridge above that so the
// tool's own timeout wins instead of a generic bridge timeout.
const CALL_TIMEOUT_MS = Number(process.env.BRIDGE_CALL_TIMEOUT_MS || "310000");
// Public origin ChatGPT uses; only used for discovery documents, no redirects.
const PUBLIC_URL = (process.env.BRIDGE_PUBLIC_URL || "").replace(/\/$/, "");
// Set only behind the OpenAI Secure MCP Tunnel: avoids OAuth challenges no client can complete.
const TRUST_TUNNEL = process.env.BRIDGE_TRUST_TUNNEL === "1";
const TOKEN_TTL_S = 3600;
const AUTHORIZE_CODE_TTL_MS = 5 * 60 * 1000;

const token = readFileSync(TOKEN_FILE, "utf8").trim();
if (!token) { console.error("empty bearer token"); process.exit(1); }
// Optional separate key for URL clients (?key=); absent file means header auth only.
const URL_KEY_FILE = process.env.BRIDGE_URL_KEY_FILE || "";
let urlKey = "";
if (URL_KEY_FILE) {
  try { urlKey = readFileSync(URL_KEY_FILE, "utf8").trim(); } catch (e) { console.error("url key read failed", e.message); }
}

function redact(value) {
  if (typeof value === "string") {
    let s = value;
    s = s.replace(/pcp_[A-Za-z0-9_-]{8,}/g, "[REDACTED_API_KEY]");
    s = s.replace(/Bearer\s+[A-Za-z0-9._~-]{12,}/gi, "Bearer [REDACTED]");
    s = s.replace(/("?(?:password|secret|token|api[_-]?key|passphrase|sudoPassword)"?\s*[:=]\s*"?)[^",\s}]{4,}("?)/gi, "$1[REDACTED]$2");
    return s.length > 4000 ? s.slice(0, 4000) + "...[truncated]" : s;
  }
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === "object") {
    const o = {};
    for (const [k, v] of Object.entries(value)) o[k] = redact(v);
    return o;
  }
  return value;
}
function audit(entry) {
  try { appendFileSync(AUDIT_FILE, JSON.stringify({ t: new Date().toISOString(), ...redact(entry) }) + "\n"); }
  catch (e) { console.error("audit write failed", e.message); }
}

// ---- OAuth (MCP authorization spec: protected-resource metadata, CIMD/none + PKCE) ----
// Tokens are HMAC-signed and in-memory-free: a restart only forces clients to reauthorize.
const MCP_PATH = "/mcp";
function base64url(buf) { return Buffer.from(buf).toString("base64url"); }
function hmac(input) { return createHash("sha256").update(token).update("\0").update(input).digest(); }
function signToken(exp) {
  const payload = base64url(JSON.stringify({ exp, jti: randomBytes(9).toString("base64url") }));
  return `${payload}.${base64url(hmac(payload))}`;
}
function validToken(tok) {
  const dot = tok.indexOf(".");
  if (dot <= 0) return false;
  const payload = tok.slice(0, dot);
  if (!check(tok.slice(dot + 1), base64url(hmac(payload)))) return false;
  try { return JSON.parse(Buffer.from(payload, "base64url").toString()).exp > Date.now() / 1000; }
  catch { return false; }
}
// One-time authorization codes: code -> { challenge, resource, exp }.
const codes = new Map();
function pruneCodes() {
  const now = Date.now();
  for (const [code, entry] of codes) if (entry.exp < now) codes.delete(code);
}
const PUBLIC_ORIGIN = () => PUBLIC_URL || "https://ubuntu-mcp-chat.zariszlif.pl";
function resourceMetadataUrl() {
  return `${PUBLIC_ORIGIN()}/.well-known/oauth-protected-resource${MCP_PATH}`;
}
function challenge(res) {
  if (TRUST_TUNNEL) return;
  res.setHeader("www-authenticate", `Bearer resource_metadata="${resourceMetadataUrl()}", scope="mcp"`);
}
function sendJson(res, status, body) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store", ...corsHeaders() });
  res.end(JSON.stringify(body));
}
function corsHeaders() {
  return {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "authorization, content-type, mcp-protocol-version, mcp-session-id",
    "access-control-expose-headers": "www-authenticate, mcp-session-id",
  };
}
function page(html) {
  return `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ubuntu MCP - authorize</title>
<style>body{font:16px system-ui;max-width:32rem;margin:3rem auto;padding:0 1rem}code{word-break:break-all}label,input,button{display:block;width:100%;box-sizing:border-box;margin:.4rem 0;padding:.5rem}button{cursor:pointer}small{color:#555}</style>${html}`;
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function authorizePage(params, error) {
  const q = new URLSearchParams(params).toString();
  return page(`<h1>Ubuntu MCP</h1>
<p>ChatGPT asks for SSH access to the Ubuntu host through this bridge. Enter the bridge URL key to approve. It is not sent to ChatGPT.</p>
${error ? `<p><strong>${escapeHtml(error)}</strong></p>` : ""}
<form method="POST" action="/authorize?${escapeHtml(q)}">
<label>URL key <input type="password" name="key" autocomplete="current-password" required autofocus></label>
<button type="submit">Authorize</button></form>
<small>Scope: ${escapeHtml(params.scope || "mcp")} · redirect: <code>${escapeHtml(params.redirect_uri || "")}</code></small>`);
}
function redirectAllowed(uri) {
  try {
    const u = new URL(uri);
    // Only OpenAI's connector callbacks: the authorize form is where the URL key is entered.
    return u.protocol === "https:" &&
      (u.hostname === "chatgpt.com" || u.hostname.endsWith(".chatgpt.com")) &&
      (u.pathname === "/connector_platform_oauth_redirect" || u.pathname.startsWith("/connector/oauth/"));
  } catch { return false; }
}
function authorizeParams(u) {
  const p = u.searchParams;
  return {
    response_type: p.get("response_type") || "",
    client_id: p.get("client_id") || "",
    redirect_uri: p.get("redirect_uri") || "",
    state: p.get("state") || "",
    code_challenge: p.get("code_challenge") || "",
    code_challenge_method: p.get("code_challenge_method") || "",
    resource: p.get("resource") || "",
    scope: p.get("scope") || "",
  };
}
function redirectWith(params, values) {
  const target = new URL(params.redirect_uri);
  for (const [k, v] of Object.entries(values)) if (v) target.searchParams.set(k, v);
  return target.toString();
}
function check(got, want) {
  if (!got || !want) return false;
  const a = Buffer.from(got); const b = Buffer.from(want);
  return a.length === b.length && timingSafeEqual(a, b);
}

// ---- stdio child supervision (single channel, serialized queue) ----
let child = null;
let seq = 0;
const pending = new Map(); // id -> {resolve,reject,timer,payload}
let buf = "";
function startChild() {
  child = spawn(CHILD_CMD, CHILD_ARGS, { stdio: ["pipe", "pipe", "inherit"] });
  child.on("exit", (code) => {
    for (const [, p] of pending) { clearTimeout(p.timer); p.reject(new Error(`child exited (${code})`)); }
    pending.clear();
    setTimeout(() => { console.error("respawning stdio child"); startChild(); }, 1000);
  });
  child.stdout.on("data", (d) => {
    buf += d.toString();
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line) continue;
      let msg; try { msg = JSON.parse(line); } catch { continue; }
      const p = msg.id !== undefined ? pending.get(String(msg.id)) : null;
      if (p) { clearTimeout(p.timer); pending.delete(String(msg.id)); p.resolve(msg); }
    }
  });
}
startChild();

function childCall(payload) {
  return new Promise((resolve, reject) => {
    if (!child || child.exitCode !== null) return reject(new Error("child unavailable"));
    const id = payload.id ?? `b${++seq}`;
    const msg = { ...payload, id };
    const timer = setTimeout(() => { pending.delete(String(id)); reject(new Error("child call timeout")); }, CALL_TIMEOUT_MS);
    pending.set(String(id), { resolve, reject, timer });
    child.stdin.write(JSON.stringify(msg) + "\n", (e) => { if (e) { clearTimeout(timer); pending.delete(String(id)); reject(e); } });
  });
}
function childNotify(payload) {
  if (child && child.exitCode === null) child.stdin.write(JSON.stringify(payload) + "\n");
}
// mcp-ssh-manager keeps one shared SSH connection per stdio child, so tools/call
// requests are serialized; the call timeout starts when the call runs, not in queue.
let callQueue = Promise.resolve();
function childCallQueued(payload) {
  const run = () => childCall(payload);
  const queued = callQueue.then(run, run);
  callQueue = queued.then(() => undefined, () => undefined);
  return queued;
}

// ---- HTTP ----
function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []; let n = 0;
    req.on("data", (c) => { chunks.push(c); n += c.length; if (n > 4 * 1024 * 1024) { req.destroy(); reject(new Error("body too large")); } });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}
function requestPath(req) {
  try { return new URL(req.url, "http://localhost").pathname; } catch { return req.url; }
}
function authed(req) {
  // Both secrets are equally trusted: the bridge bearer (header-native clients)
  // and the URL key (query-native clients). Accept either one in either place.
  const wanted = [token, urlKey].filter(Boolean);
  const h = req.headers.authorization || "";
  if (h.startsWith("Bearer ")) {
    const got = h.slice(7);
    if (wanted.some((want) => check(got, want))) return true;
    if (validToken(got)) return true;
  }
  try {
    const u = new URL(req.url, "http://localhost");
    const k = u.searchParams.get("key") || u.searchParams.get("token");
    return wanted.some((want) => check(k, want));
  } catch { return false; }
}

function handleOAuth(req, res, path) {
  const origin = PUBLIC_ORIGIN();
  if (path === "/.well-known/oauth-protected-resource" || path === "/.well-known/oauth-protected-resource/mcp") {
    sendJson(res, 200, {
      resource: `${origin}${MCP_PATH}`,
      authorization_servers: [origin],
      scopes_supported: ["mcp"],
      resource_documentation: `${origin}/`,
    });
    return true;
  }
  if (path === "/.well-known/oauth-authorization-server" || path === "/.well-known/oauth-authorization-server/mcp") {
    sendJson(res, 200, {
      issuer: origin,
      authorization_endpoint: `${origin}/authorize`,
      token_endpoint: `${origin}/token`,
      response_types_supported: ["code"],
      grant_types_supported: ["authorization_code"],
      code_challenge_methods_supported: ["S256"],
      token_endpoint_auth_methods_supported: ["none"],
      scopes_supported: ["mcp"],
    });
    return true;
  }
  return false;
}

const server = createServer(async (req, res) => {
  const path = requestPath(req);
  const url = new URL(req.url, "http://localhost");
  if (req.method === "OPTIONS") { res.writeHead(204, corsHeaders()); res.end(); return; }
  if (path === "/healthz" && req.method === "GET") {
    const ok = child && child.exitCode === null;
    res.writeHead(ok ? 200 : 503, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok, service: "ubuntu-mcp-bridge", sshManager: "3.8.6", childAlive: ok, pending: pending.size, oauth: true, tunnel: TRUST_TUNNEL }));
    return;
  }
  if (req.method === "GET" && handleOAuth(req, res, path)) return;

  if (path === "/authorize") {
    pruneCodes();
    const params = authorizeParams(url);
    if (params.response_type !== "code" || !params.redirect_uri || !params.code_challenge || params.code_challenge_method !== "S256") {
      sendJson(res, 400, { error: "invalid_request", error_description: "authorization code + PKCE S256 required" });
      return;
    }
    if (!redirectAllowed(params.redirect_uri)) {
      sendJson(res, 400, { error: "invalid_request", error_description: "redirect_uri not allowed" });
      return;
    }
    if (req.method === "GET") {
      res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
      res.end(authorizePage(params, ""));
      return;
    }
    if (req.method === "POST") {
      let action;
      try { action = new URLSearchParams(await readBody(req)); }
      catch { sendJson(res, 400, { error: "invalid_request" }); return; }
      if (![token, urlKey].filter(Boolean).some((want) => check(action.get("key") || "", want))) {
        audit({ event: "oauth_authorize_denied", client_id: params.client_id.slice(0, 120), ua: String(req.headers["user-agent"] || "").slice(0, 120) });
        res.writeHead(401, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
        res.end(authorizePage(params, "Wrong URL key."));
        return;
      }
      const code = randomBytes(24).toString("base64url");
      codes.set(code, { challenge: params.code_challenge, resource: params.resource, exp: Date.now() + AUTHORIZE_CODE_TTL_MS });
      audit({ event: "oauth_authorize", client_id: params.client_id.slice(0, 120), resource: params.resource.slice(0, 200) });
      res.writeHead(302, { location: redirectWith(params, { code, state: params.state }), "cache-control": "no-store" });
      res.end();
      return;
    }
    sendJson(res, 405, { error: "method_not_allowed" });
    return;
  }

  if (path === "/token" && req.method === "POST") {
    let form;
    try { form = new URLSearchParams(await readBody(req)); }
    catch { sendJson(res, 400, { error: "invalid_request" }); return; }
    const entry = codes.get(form.get("code") || "");
    codes.delete(form.get("code") || "");
    if (form.get("grant_type") !== "authorization_code" || !entry || entry.exp < Date.now()) {
      sendJson(res, 400, { error: "invalid_grant" });
      return;
    }
    const verifier = form.get("code_verifier") || "";
    const challenge = createHash("sha256").update(verifier).digest("base64url");
    if (!check(challenge, entry.challenge)) { sendJson(res, 400, { error: "invalid_grant", error_description: "PKCE mismatch" }); return; }
    if (entry.resource && form.get("resource") && entry.resource !== form.get("resource")) {
      sendJson(res, 400, { error: "invalid_grant", error_description: "resource mismatch" });
      return;
    }
    sendJson(res, 200, { access_token: signToken(Math.floor(Date.now() / 1000) + TOKEN_TTL_S), token_type: "Bearer", expires_in: TOKEN_TTL_S, scope: "mcp" });
    return;
  }

  if (path !== "/mcp" || req.method !== "POST") {
    res.writeHead(404, { "content-type": "application/json" }); res.end(JSON.stringify({ error: "not_found" })); return;
  }
  if (!authed(req)) {
    const h = req.headers.authorization || "";
    const scheme = h ? h.split(" ")[0] : "none";
    // path without the query string: the URL key must never reach the audit log.
    audit({ event: "http_auth_denied", scheme, ua: String(req.headers["user-agent"] || "").slice(0, 120), path, method: req.method });
    challenge(res);
    res.writeHead(401, { "content-type": "application/json" }); res.end(JSON.stringify({ error: "unauthorized" })); return;
  }
  let payload;
  try { payload = JSON.parse(await readBody(req)); }
  catch { res.writeHead(400, { "content-type": "application/json" }); res.end(JSON.stringify({ error: "bad_json" })); return;
  }
  const t0 = Date.now();
  const isCall = payload.method === "tools/call" && payload.params?.name;
  try {
    if (payload.id === undefined) { childNotify(payload); res.writeHead(202, { "content-type": "application/json" }); res.end(JSON.stringify({ ok: true })); return; }
    const out = await (isCall ? childCallQueued(payload) : childCall(payload));
    if (isCall) {
      const err = out.error ? String(out.error.message || out.error).slice(0, 500) : null;
      audit({ event: "tool_call", tool: payload.params.name, args: payload.params.arguments || {}, error: err, ms: Date.now() - t0, pending: pending.size });
    }
    res.writeHead(200, { "content-type": "application/json" }); res.end(JSON.stringify(out));
  } catch (e) {
    if (isCall) audit({ event: "tool_call", tool: payload.params.name, args: payload.params.arguments || {}, error: String(e.message).slice(0, 500), ms: Date.now() - t0 });
    res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ jsonrpc: "2.0", id: payload.id ?? null, error: { code: -32000, message: `bridge: ${e.message}` } }));
  }
});
server.listen(PORT, "0.0.0.0", () => console.log(`ubuntu-mcp-bridge listening on 0.0.0.0:${PORT} (private container networks only, no published ports)`));