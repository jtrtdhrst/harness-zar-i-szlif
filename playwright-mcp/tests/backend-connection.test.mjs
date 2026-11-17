// Regression: the idle proxy must use a dedicated backend socket per proxied
// request.
//
// Observed in production shape (real @playwright/mcp backend, 2026-11-17): with
// socket reuse the second MCP call on a session returned a bare empty-body HTTP
// 400 and GET /mcp (the client-held SSE channel) answered 400 as well —
// 200/400/200/400 for four identical browser_navigate calls. With one fresh
// socket per request the same sequence is 200/200/200/200 and the GET stream
// opens. The backend keeps a POST response stream per connection, so a reused
// keep-alive socket cannot carry the next request.
//
// The stub backend reports which socket served each call, so the assertion is
// about the calls themselves rather than about proxy bookkeeping. The negative
// control re-runs the same scenario against a copy of the proxy with
// `agent: false` removed: it must reuse sockets, which is what makes the
// positive assertion meaningful.
import assert from "node:assert/strict";
import test from "node:test";
import { spawn } from "node:child_process";
import { createServer, request } from "node:http";
import { once } from "node:events";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";

const here = dirname(fileURLToPath(import.meta.url));
const PROXY_FILE = process.env.PROXY_FILE || join(here, "..", "idle-proxy.cjs");
const BACKEND = join(here, "fixtures", "counting-mcp-backend.mjs");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function freePort() {
  const srv = createServer();
  srv.listen(0, "127.0.0.1");
  await once(srv, "listening");
  const { port } = srv.address();
  srv.close();
  await once(srv, "close");
  return port;
}

function post(port, body, sid) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const headers = { "content-type": "application/json", accept: "application/json, text/event-stream",
      "content-length": Buffer.byteLength(payload) };
    if (sid) headers["mcp-session-id"] = sid;
    const req = request({ host: "127.0.0.1", port, path: "/mcp", method: "POST", headers, timeout: 30000 }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, text: Buffer.concat(chunks).toString() }));
    });
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", reject);
    req.end(payload);
  });
}

async function health(port) {
  return new Promise((resolve) => {
    const req = request({ host: "127.0.0.1", port, path: "/healthz", timeout: 2000 }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve(res.statusCode));
    });
    req.on("timeout", () => { req.destroy(); resolve(0); });
    req.on("error", () => resolve(0));
    req.end();
  });
}

// Initialize one session, then drive `calls` sequential MCP calls through the
// proxy and report the backend sockets that served them.
async function driveProxy(proxyFile, calls) {
  const port = await freePort();
  const dir = mkdtempSync(join(tmpdir(), "pw-conn-"));
  const logFile = join(dir, "connections.log");
  const proxy = spawn(process.execPath, [proxyFile], {
    env: { ...process.env, LISTEN_PORTS: String(port), BACKEND_ENTRY: BACKEND, CONN_LOG: logFile, IDLE_SECONDS: "600" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let logs = "";
  proxy.stderr.on("data", (d) => { logs += String(d); });
  proxy.stdout.on("data", (d) => { logs += String(d); });

  try {
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline) {
      if (await health(port)) break;
      await sleep(200);
    }
    assert.ok(await health(port), `proxy did not start: ${logs.slice(-800)}`);

    const init = await post(port, { jsonrpc: "2.0", id: 0, method: "initialize",
      params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "conn-test", version: "1" } } });
    assert.equal(init.status, 200, `initialize failed: ${init.text.slice(0, 400)}`);
    const sid = init.headers["mcp-session-id"];
    assert.ok(sid, "stub backend must hand out a session id");

    const statuses = [];
    const connIds = [];
    for (let i = 0; i < calls; i++) {
      const r = await post(port, { jsonrpc: "2.0", id: i + 1, method: "tools/call",
        params: { name: "browser_navigate", arguments: { url: "data:text/html,<title>t</title>" } } }, sid);
      statuses.push(r.status);
      try { connIds.push(JSON.parse(r.text).result.conn); } catch { connIds.push(`status-${r.status}`); }
      // small gap: a real client does not pipeline browser calls back to back
      await sleep(150);
    }

    const log = existsSync(logFile) ? readFileSync(logFile, "utf8") : "";
    const connections = new Set(log.split("\n").filter((l) => l.startsWith("conn ")).map((l) => l.slice(5).trim())).size;
    return { statuses, connIds, connections };
  } finally {
    proxy.kill("SIGTERM");
    await Promise.race([once(proxy, "exit"), sleep(3000)]);
    if (proxy.exitCode === null) proxy.kill("SIGKILL");
  }
}

test("repeated calls on one session each get their own backend socket and succeed", async () => {
  const { statuses, connIds, connections } = await driveProxy(PROXY_FILE, 4);
  assert.deepEqual(statuses, [200, 200, 200, 200], "repeated calls on one session must all succeed");
  assert.equal(new Set(connIds).size, 4,
    `each call must be served over a fresh backend socket; sockets seen: ${connIds.join(",")} (total ${connections})`);
});

test("NEGATIVE CONTROL: a reusing proxy shares one socket across calls", async () => {
  const source = readFileSync(PROXY_FILE, "utf8");
  const reusing = source
    .replace(/, agent: false/g, "")
    .replace(/\n\s*agent: false,/g, "");
  assert.notEqual(reusing, source, "the negative control must actually remove the dedicated-socket rule");
  const dir = mkdtempSync(join(tmpdir(), "pw-proxy-reuse-"));
  const candidate = join(dir, "idle-proxy-reuse.cjs");
  writeFileSync(candidate, reusing);

  const { connIds } = await driveProxy(candidate, 4);
  assert.ok(new Set(connIds).size < 4,
    `a keep-alive-reusing proxy must share sockets, but every call reported a distinct one: ${connIds.join(",")}`);
});
