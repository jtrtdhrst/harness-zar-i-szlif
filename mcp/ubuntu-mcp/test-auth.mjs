// Self-check for the bridge auth boundary: run `node test-auth.mjs`.
// Starts server.mjs with a stub stdio child and asserts header, URL-key and
// denial behaviour, plus that the URL key never reaches the audit log.
import { spawn } from "node:child_process";
import { generateKeyPairSync, sign } from "node:crypto";
import { createServer as createHttpServer } from "node:http";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dir = mkdtempSync(join(tmpdir(), "ubuntu-mcp-auth-"));
// Local JWKS so a real RS256 Access JWT can be verified without Cloudflare.
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const testJwk = { ...publicKey.export({ format: "jwk" }), kid: "test-key", use: "sig", alg: "RS256" };
const jwksServer = createHttpServer((_req, res) => {
  res.writeHead(200, { "content-type": "application/json" });
  res.end(JSON.stringify({ keys: [testJwk] }));
});
await new Promise((resolve) => jwksServer.listen(0, "127.0.0.1", resolve));
const jwksPort = jwksServer.address().port;
const b64u = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
function signedAccessJwt() {
  const h = b64u({ alg: "RS256", typ: "JWT", kid: "test-key" });
  const now = Math.floor(Date.now() / 1000);
  const p = b64u({
    iss: "https://flashautomate.cloudflareaccess.com",
    aud: "5908b33b5935031208517367fa5712b49fb68f1b9ee8233d0584b9c3fcf29201",
    sub: "owner@example.com", email: "owner@example.com", iat: now, exp: now + 3600,
  });
  return `${h}.${p}.${sign("RSA-SHA256", Buffer.from(h + "." + p), privateKey).toString("base64url")}`;
}
const TOKEN = "test-bearer-token-0123456789";
const URL_KEY = "test-url-key-0123456789abcdef";
for (const [name, value] of [["token", TOKEN], ["key", URL_KEY]]) writeFileSync(join(dir, name), value + "\n");
writeFileSync(join(dir, "child.mjs"), `
process.stdin.on("data", (d) => {
  for (const line of d.toString().split("\\n")) {
    if (!line.trim()) continue;
    const msg = JSON.parse(line);
    if (msg.id !== undefined) process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: msg.id, result: { ok: true } }) + "\\n");
  }
});
`);
const port = 18000 + Math.floor(Math.random() * 2000);
const server = spawn(process.execPath, [join(here, "server.mjs")], {
  env: {
    ...process.env, BRIDGE_PORT: String(port),
    BRIDGE_PUBLIC_URL: `http://127.0.0.1:${port}`,
    BRIDGE_TOKEN_FILE: join(dir, "token"), BRIDGE_URL_KEY_FILE: join(dir, "key"),
    BRIDGE_ACCESS_JWKS_URL: `http://127.0.0.1:${jwksPort}/certs`,
    BRIDGE_AUDIT_FILE: join(dir, "audit.jsonl"),
    BRIDGE_CHILD_CMD: process.execPath, BRIDGE_CHILD_ARGS: join(dir, "child.mjs"),
  },
  stdio: ["ignore", "pipe", "inherit"],
});

const url = `http://127.0.0.1:${port}`;
const body = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} });
async function call(path, headers = {}) {
  const response = await fetch(url + path, { method: "POST", headers: { "content-type": "application/json", ...headers }, body });
  return response.status;
}

let failed = 0;
function expect(name, actual, want) {
  if (actual !== want) { failed++; console.log(`FAIL ${name}: got ${actual}, want ${want}`); }
  else console.log(`ok   ${name}`);
}
async function oauthFlow(verifier, key) {
  const challenge = (await import("node:crypto")).createHash("sha256").update(verifier).digest("base64url");
  const authorize = new URLSearchParams({
    response_type: "code", client_id: "https://chatgpt.com/oauth/client.json",
    redirect_uri: "https://chatgpt.com/connector_platform_oauth_redirect", state: "st-1",
    code_challenge: challenge, code_challenge_method: "S256",
    resource: `http://127.0.0.1:${port}/mcp`, scope: "mcp",
  });
  const form = new URLSearchParams({ key });
  const authRes = await fetch(`${url}/authorize?${authorize}`, {
    method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: form, redirect: "manual",
  });
  return { authRes, authorize };
}

try {
  for (let i = 0; i < 50; i++) {
    try { await fetch(url + "/healthz"); break; } catch { await new Promise((r) => setTimeout(r, 100)); }
  }
  expect("POST /mcp no auth", await call("/mcp"), 401);
  expect("POST /mcp?key=<url-key>", await call(`/mcp?key=${URL_KEY}`), 200);
  expect("POST /mcp?token=<url-key>", await call(`/mcp?token=${URL_KEY}`), 200);
  expect("POST /mcp?key=<bearer>", await call(`/mcp?key=${TOKEN}`), 200);
  expect("POST /mcp Bearer <bearer>", await call("/mcp", { authorization: `Bearer ${TOKEN}` }), 200);
  expect("POST /mcp Bearer <url-key>", await call("/mcp", { authorization: `Bearer ${URL_KEY}` }), 200);
  expect("POST /mcp?key=wrong", await call("/mcp?key=wrong"), 401);
  expect("GET /healthz", (await fetch(url + "/healthz")).status, 200);
  expect("GET /mcp?key=<url-key>", (await fetch(`${url}/mcp?key=${URL_KEY}`)).status, 405);

  const meta = await fetch(url + "/.well-known/oauth-protected-resource");
  const metaJson = await meta.json();
  expect("GET protected-resource metadata", meta.status, 200);
  expect("metadata resource is /mcp", metaJson.resource, `${url}/mcp`);
  const as = await fetch(url + "/.well-known/oauth-authorization-server");
  const asJson = await as.json();
  expect("GET authorization-server metadata", as.status, 200);
  expect("metadata advertises S256", (asJson.code_challenge_methods_supported || []).includes("S256"), true);
  expect("metadata token auth none", (asJson.token_endpoint_auth_methods_supported || []).includes("none"), true);
  expect("metadata advertises CIMD", asJson.client_id_metadata_document_supported, true);

  const unauthorized = await fetch(url + "/mcp", { method: "POST", headers: { "content-type": "application/json" }, body });
  expect("401 carries resource_metadata", /resource_metadata=/.test(unauthorized.headers.get("www-authenticate") || ""), true);

  const formFlow = await oauthFlow("form-verifier", URL_KEY);
  expect("GET /authorize form", (await fetch(`${url}/authorize?${formFlow.authorize}`)).status, 200);
  // A spoofed/unsigned Access JWT must never grant approval (no form bypass).
  const spoofedJwt = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImZha2UifQ.eyJzdWIiOiJhdHRhY2tlciIsImF1ZCI6IjU5MDhiMzNiNTkzNTAzMTIwODUxNzM2N2ZhNTcxMmI0OWZiNjhmMWI5ZWU4MjMzZDA1ODRiOWMzZmNmMjkyMDEiLCJpc3MiOiJodHRwczovL2ZsYXNoYXV0b21hdGUuY2xvdWRmbGFyZWFjY2Vzcy5jb20ifQ.fake-signature";
  expect("GET /authorize spoofed Access JWT stays form", (await fetch(`${url}/authorize?${formFlow.authorize}`, { headers: { "cf-access-jwt-assertion": spoofedJwt } })).status, 200);
  expect("POST /authorize spoofed Access JWT rejected", (await fetch(`${url}/authorize?${formFlow.authorize}`, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded", "cf-access-jwt-assertion": spoofedJwt }, body: new URLSearchParams({ key: "wrong" }), redirect: "manual" })).status, 401);
  // A correctly signed Access JWT (the One-time PIN flow) grants approval.
  const accessFlow = await oauthFlow("access-verifier", "irrelevant");
  const accessRes = await fetch(`${url}/authorize?${accessFlow.authorize}`, { headers: { "cf-access-jwt-assertion": signedAccessJwt() }, redirect: "manual" });
  expect("GET /authorize valid Access JWT -> redirect", accessRes.status, 302);
  const accessCode = new URL(accessRes.headers.get("location") || "").searchParams.get("code");
  expect("Access JWT issues a code", Boolean(accessCode), true);
  expect("POST /authorize wrong key", (await oauthFlow("verifier-1", "wrong")).authRes.status, 401);
  const evil = new URLSearchParams({
    response_type: "code", client_id: "x", redirect_uri: "https://evil.example/cb", state: "s",
    code_challenge: "abc", code_challenge_method: "S256", scope: "mcp",
  });
  expect("foreign redirect_uri rejected", (await fetch(`${url}/authorize?${evil}`)).status, 400);
  const goodFlow = await oauthFlow("verifier-2", URL_KEY);
  const location = goodFlow.authRes.headers.get("location") || "";
  const code = new URL(location).searchParams.get("code");
  expect("POST /authorize issues code", Boolean(code), true);
  expect("authorize returns state", new URL(location).searchParams.get("state"), "st-1");
  expect("authorize returns iss", new URL(location).searchParams.get("iss"), `${url}`);

  async function token(codeValue, verifier) {
    const res = await fetch(url + "/token", {
      method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ grant_type: "authorization_code", code: codeValue, code_verifier: verifier, resource: `${url}/mcp` }),
    });
    return { status: res.status, body: await res.json() };
  }
  const fresh = await oauthFlow("verifier-3", URL_KEY);
  const freshCode = new URL(fresh.authRes.headers.get("location")).searchParams.get("code");
  const issued = await token(freshCode, "verifier-3");
  expect("POST /token PKCE exchange", issued.status, 200);
  expect("token response has refresh_token", typeof issued.body.refresh_token === "string" && issued.body.refresh_token.length > 20, true);
  expect("token response token_type Bearer", issued.body.token_type, "Bearer");
  expect("access token accepted", await call("/mcp", { authorization: `Bearer ${issued.body.access_token}` }), 200);
  // refresh token is domain-separated: it must NOT be accepted as an access token.
  expect("refresh token rejected as access", await call("/mcp", { authorization: `Bearer ${issued.body.refresh_token}` }), 401);
  const refreshed = await fetch(url + "/token", {
    method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "refresh_token", refresh_token: issued.body.refresh_token }),
  });
  expect("refresh grant returns access token", refreshed.status, 200);
  const refreshedJson = await refreshed.json();
  expect("refreshed access token accepted", await call("/mcp", { authorization: `Bearer ${refreshedJson.access_token}` }), 200);
  expect("code is single-use", (await token(freshCode, "verifier-3")).status, 400);
  expect("wrong verifier rejected", (await token(code, "nope")).body.error, "invalid_grant");
  expect("garbage token rejected", await call("/mcp", { authorization: "Bearer abc.def" }), 401);

  const audit = readFileSync(join(dir, "audit.jsonl"), "utf8");
  expect("audit has no secrets", audit.includes(TOKEN) || audit.includes(URL_KEY), false);
} finally {
  server.kill();
  jwksServer.close();
}
process.exit(failed ? 1 : 0);
