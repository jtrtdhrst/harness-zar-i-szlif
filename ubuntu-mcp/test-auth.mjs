// Self-check for the bridge auth boundary: run `node test-auth.mjs`.
// Starts server.mjs with a stub stdio child and asserts header, URL-key and
// denial behaviour, plus that the URL key never reaches the audit log.
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dir = mkdtempSync(join(tmpdir(), "ubuntu-mcp-auth-"));
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
  expect("GET /mcp?key=<url-key>", (await fetch(`${url}/mcp?key=${URL_KEY}`)).status, 404);

  const meta = await fetch(url + "/.well-known/oauth-protected-resource");
  const metaJson = await meta.json();
  expect("GET protected-resource metadata", meta.status, 200);
  expect("metadata resource is /mcp", metaJson.resource, `${url}/mcp`);
  const as = await fetch(url + "/.well-known/oauth-authorization-server");
  const asJson = await as.json();
  expect("GET authorization-server metadata", as.status, 200);
  expect("metadata advertises S256", (asJson.code_challenge_methods_supported || []).includes("S256"), true);
  expect("metadata token auth none", (asJson.token_endpoint_auth_methods_supported || []).includes("none"), true);

  const unauthorized = await fetch(url + "/mcp", { method: "POST", headers: { "content-type": "application/json" }, body });
  expect("401 carries resource_metadata", /resource_metadata=/.test(unauthorized.headers.get("www-authenticate") || ""), true);

  const formFlow = await oauthFlow("form-verifier", URL_KEY);
  expect("GET /authorize form", (await fetch(`${url}/authorize?${formFlow.authorize}`)).status, 200);
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
  expect("access token accepted", await call("/mcp", { authorization: `Bearer ${issued.body.access_token}` }), 200);
  expect("code is single-use", (await token(freshCode, "verifier-3")).status, 400);
  expect("wrong verifier rejected", (await token(code, "nope")).body.error, "invalid_grant");
  expect("garbage token rejected", await call("/mcp", { authorization: "Bearer abc.def" }), 401);

  const audit = readFileSync(join(dir, "audit.jsonl"), "utf8");
  expect("audit has no secrets", audit.includes(TOKEN) || audit.includes(URL_KEY), false);
} finally {
  server.kill();
}
process.exit(failed ? 1 : 0);
