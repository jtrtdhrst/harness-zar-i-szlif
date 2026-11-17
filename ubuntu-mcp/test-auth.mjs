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
  const audit = readFileSync(join(dir, "audit.jsonl"), "utf8");
  expect("audit has no secrets", audit.includes(TOKEN) || audit.includes(URL_KEY), false);
} finally {
  server.kill();
}
process.exit(failed ? 1 : 0);
