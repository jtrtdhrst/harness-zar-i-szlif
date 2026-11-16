// Regression suite for playwright-mcp/idle-proxy.cjs.
//
// The reported production failure class was: a single failed MCP call (or an
// idle tick landing on a live session) tore the whole backend down, so the
// next call re-initialized a fresh process with a fresh browser context —
// observed as "Session not found" / "transport session expired" and a page
// reset to about:blank. These tests drive the real proxy against a stub
// streamable-HTTP backend that models a per-session browser context and a
// backend process identity (pid).
//
// PROXY_FILE lets the suite be pointed at a candidate copy of the proxy for
// before/after evidence; the committed default is the shipped file.
import assert from "node:assert/strict";
import test from "node:test";
import { spawn } from "node:child_process";
import { createServer, request } from "node:http";
import { once } from "node:events";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdtempSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";

const here = dirname(fileURLToPath(import.meta.url));
const PROXY_FILE = process.env.PROXY_FILE || join(here, "..", "idle-proxy.cjs");
const STUB = join(here, "fixtures", "stub-mcp-backend.mjs");

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

async function startProxy({ idleSeconds = 600, requestTimeoutMs, stubSilent = false } = {}) {
  const port = await freePort();
  const dir = mkdtempSync(join(tmpdir(), "pw-proxy-"));
  const startsFile = join(dir, "backend-starts.log");
  const proxy = spawn(process.execPath, [PROXY_FILE], {
    env: {
      ...process.env,
      IDLE_SECONDS: String(idleSeconds),
      LISTEN_PORTS: String(port),
      BACKEND_ENTRY: STUB,
      STUB_STARTS_FILE: startsFile,
      ...(requestTimeoutMs ? { REQUEST_TIMEOUT_MS: String(requestTimeoutMs) } : {}),
      ...(stubSilent ? { STUB_SILENT: "1" } : {}),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stderr = "";
  proxy.stderr.on("data", (d) => { stderr += String(d); });
  proxy.stdout.on("data", (d) => { stderr += String(d); });

  const deadline = Date.now() + 15000;
  for (;;) {
    try {
      const h = await jsonRequest(port, { method: "GET", path: "/healthz" });
      if (h.status === 200) break;
    } catch {
      /* not listening yet */
    }
    if (Date.now() > deadline) throw new Error(`proxy did not start:\n${stderr}`);
    await sleep(100);
  }
  return {
    port,
    stderr: () => stderr,
    starts: () => (existsSync(startsFile) ? readFileSync(startsFile, "utf8").trim().split("\n").filter(Boolean) : []),
    async stop() {
      proxy.kill("SIGTERM");
      await Promise.race([once(proxy, "exit"), sleep(3000)]);
      try { proxy.kill("SIGKILL"); } catch { /* already gone */ }
    },
  };
}

function jsonRequest(port, { method = "POST", path = "/mcp", headers = {}, body, timeout = 90000 }) {
  return new Promise((resolve, reject) => {
    const req = request({ host: "127.0.0.1", port, method, path, headers, timeout, agent: false }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => {
        const raw = Buffer.concat(chunks).toString("utf8");
        let parsed = null;
        try { parsed = JSON.parse(raw); } catch { /* SSE or empty */ }
        resolve({ status: res.statusCode, headers: res.headers, raw, json: parsed });
      });
    });
    req.on("timeout", () => req.destroy(new Error("client timeout")));
    req.on("error", reject);
    if (body !== undefined) req.write(JSON.stringify(body));
    req.end();
  });
}

const mcp = (port, { sid, method, params, id = 1, timeout } = {}) =>
  jsonRequest(port, {
    timeout,
    headers: {
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
      ...(sid ? { "mcp-session-id": sid } : {}),
    },
    body: { jsonrpc: "2.0", id, method, ...(params ? { params } : {}) },
  });

async function initialize(port) {
  const res = await mcp(port, {
    method: "initialize",
    params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "proxy-test", version: "1" } },
  });
  assert.equal(res.status, 200, `initialize failed: ${res.status} ${res.raw}`);
  const sid = res.headers["mcp-session-id"];
  assert.ok(sid, "initialize returned no mcp-session-id");
  await mcp(port, { method: "notifications/initialized", id: undefined, sid }).catch(() => {});
  return String(sid);
}

const toolCall = (port, sid, name, args = {}, timeout) =>
  mcp(port, { sid, method: "tools/call", params: { name, arguments: args }, timeout });

/** Parsed tool payload, or a descriptive failure. */
function payload(res, name) {
  assert.equal(res.status, 200, `${name} failed: ${res.status} ${res.raw.slice(0, 200)}`);
  const text = res.json?.result?.content?.[0]?.text;
  assert.ok(text, `${name} returned no content: ${res.raw.slice(0, 200)}`);
  return JSON.parse(text);
}

test("sequential calls keep one backend process and one browser state", async () => {
  const p = await startProxy();
  try {
    const sid = await initialize(p.port);
    const before = payload(await toolCall(p.port, sid, "state"), "state");
    assert.equal(before.url, "about:blank");
    await toolCall(p.port, sid, "navigate", { url: "http://example.test/page-a" });
    const after = payload(await toolCall(p.port, sid, "state"), "state");
    assert.equal(after.pid, before.pid, "backend process changed between two successful calls");
    assert.equal(after.url, "http://example.test/page-a", "browser state was lost between calls");
    assert.equal(p.starts().length, 1, "backend was spawned more than once");
  } finally {
    await p.stop();
  }
});

test("one failed call does not reset the session or the browser context", async () => {
  const p = await startProxy();
  try {
    const sid = await initialize(p.port);
    await toolCall(p.port, sid, "navigate", { url: "http://example.test/keep-me" });
    const before = payload(await toolCall(p.port, sid, "state"), "state");

    // Transport-level failure on a single call (socket dropped mid-request).
    const boom = await toolCall(p.port, sid, "boom").catch((e) => ({ status: 0, raw: String(e) }));
    assert.ok(boom.status === 502 || boom.status === 0, `unexpected boom response: ${boom.status}`);

    const after = await toolCall(p.port, sid, "state");
    assert.equal(after.status, 200, `session was destroyed by one failed call: ${after.status} ${after.raw.slice(0, 160)}`);
    const state = payload(after, "state");
    assert.equal(state.pid, before.pid, "backend process was replaced after a single failed call");
    assert.equal(state.url, "http://example.test/keep-me", "browser context was reset to about:blank by an unrelated failure");
    assert.equal(p.starts().length, 1, "backend was respawned after a single failed call");
  } finally {
    await p.stop();
  }
});

test("one failed shared-session call does not reset the shared session", async () => {
  const p = await startProxy();
  try {
    await jsonRequest(p.port, {
      headers: { "content-type": "application/json", accept: "application/json, text/event-stream" },
      body: { jsonrpc: "2.0", id: 1, method: "tools/list" },
    });
    const before = payload(
      await jsonRequest(p.port, {
        headers: { "content-type": "application/json", accept: "application/json, text/event-stream" },
        body: { jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "navigate", arguments: { url: "http://example.test/shared" } } },
      }),
      "shared navigate",
    );
    const boom = await jsonRequest(p.port, {
      headers: { "content-type": "application/json", accept: "application/json, text/event-stream" },
      body: { jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "boom", arguments: {} } },
    }).catch((e) => ({ status: 0, raw: String(e) }));
    assert.ok(boom.status === 502 || boom.status === 0, `unexpected boom response: ${boom.status}`);

    const afterRes = await jsonRequest(p.port, {
      headers: { "content-type": "application/json", accept: "application/json, text/event-stream" },
      body: { jsonrpc: "2.0", id: 4, method: "tools/call", params: { name: "state", arguments: {} } },
    });
    assert.equal(afterRes.status, 200, `shared session was destroyed by one failed call: ${afterRes.status}`);
    const state = payload(afterRes, "shared state");
    assert.equal(state.pid, before.pid, "backend process was replaced after a single failed shared-session call");
    assert.equal(state.url, "http://example.test/shared", "shared browser context was lost after an unrelated failure");
  } finally {
    await p.stop();
  }
});

test("idle ticks never kill the backend under an in-flight call", async () => {
  const p = await startProxy({ idleSeconds: 10 });
  try {
    const sid = await initialize(p.port);
    const before = payload(await toolCall(p.port, sid, "state"), "state");
    // 18s call against a 10s idle window: the old watcher killed mid-request.
    const slow = await toolCall(p.port, sid, "slow", { ms: 18000 }, 60000);
    assert.equal(slow.status, 200, `in-flight call was terminated by the idle watcher: ${slow.status} ${slow.raw.slice(0, 160)}`);
    const after = payload(await toolCall(p.port, sid, "state"), "state");
    assert.equal(after.pid, before.pid, "backend was replaced during an in-flight call");
    assert.equal(p.starts().length, 1, "backend respawned during an in-flight call");
  } finally {
    await p.stop();
  }
});

test("a held SSE stream counts as live traffic", async () => {
  const p = await startProxy({ idleSeconds: 10 });
  try {
    const sid = await initialize(p.port);
    const before = payload(await toolCall(p.port, sid, "state"), "state");
    const stream = request(
      { host: "127.0.0.1", port: p.port, method: "GET", path: "/mcp", headers: { accept: "text/event-stream", "mcp-session-id": sid }, agent: false },
      (res) => { res.on("data", () => {}); },
    );
    stream.on("error", () => {});
    stream.end();
    await sleep(16000); // longer than the 10s idle window
    const after = await toolCall(p.port, sid, "state");
    assert.equal(after.status, 200, `held stream was not treated as activity: ${after.status} ${after.raw.slice(0, 160)}`);
    const state = payload(after, "state");
    assert.equal(state.pid, before.pid, "backend was killed while a client held a stream");
    stream.destroy();
  } finally {
    await p.stop();
  }
});

test("a SILENT client-held stream is not severed by the POST request timeout", async () => {
  // D1 regression: the proxy used to apply the POST inactivity deadline to the
  // transparent GET path, so a held SSE channel carrying no traffic (normal:
  // the server has no event yet) was destroyed after the deadline. openStreams
  // then dropped to 0 and the idle watcher could kill a backend whose browser
  // context was still live.
  const p = await startProxy({ idleSeconds: 10, requestTimeoutMs: 3000, stubSilent: true });
  try {
    const sid = await initialize(p.port);
    const before = payload(await toolCall(p.port, sid, "state"), "state");

    let ended = false;
    let status = null;
    const stream = request(
      { host: "127.0.0.1", port: p.port, method: "GET", path: "/mcp", headers: { accept: "text/event-stream", "mcp-session-id": sid }, agent: false },
      (res) => {
        status = res.statusCode;
        res.on("data", () => {});
        res.on("end", () => { ended = true; });
        res.on("close", () => { ended = true; });
      },
    );
    stream.on("error", () => { ended = true; });
    stream.end();
    await once(stream, "response");
    assert.equal(status, 200, "the transparent GET stream was not established");

    await sleep(8000); // > 2x the configured 3000 ms POST deadline
    assert.equal(ended, false, "a silent client-held SSE channel was severed by the proxy's request timeout");

    const h = await jsonRequest(p.port, { method: "GET", path: "/healthz" });
    assert.equal(h.status, 200);
    assert.equal(h.json.openStreams, 1, "a held silent stream must still count as an open stream");
    assert.equal(h.json.backend, true, "the backend was stopped while a client held a stream");

    const after = payload(await toolCall(p.port, sid, "state"), "state");
    assert.equal(after.pid, before.pid, "backend process changed while a client held a silent stream");
    stream.destroy();
  } finally {
    await p.stop();
  }
});

test("negative control: the POST request timeout still bounds a slow call", async () => {
  // The D1 fix must not disable request deadlines wholesale: a slow POST is
  // still a hung call and still returns 504 at the configured deadline.
  const p = await startProxy({ requestTimeoutMs: 1500 });
  try {
    const sid = await initialize(p.port);
    const slow = await toolCall(p.port, sid, "slow", { ms: 8000 }, 30000).catch((e) => ({ status: 0, raw: String(e) }));
    assert.equal(slow.status, 504, `a hung POST was not bounded by REQUEST_TIMEOUT_MS: ${slow.status} ${String(slow.raw).slice(0, 160)}`);
  } finally {
    await p.stop();
  }
});

test("negative control: a genuinely idle backend is still stopped", async () => {
  const p = await startProxy({ idleSeconds: 10 });
  try {
    await initialize(p.port);
    await sleep(18000); // no traffic at all
    const h = await jsonRequest(p.port, { method: "GET", path: "/healthz" });
    assert.equal(h.status, 200);
    assert.equal(h.json.backend, false, "idle backend was not stopped; the idle policy was disabled instead of made safe");
    // Diagnostics are additive; assert them only when the proxy exposes them.
    if ("inFlight" in h.json) assert.equal(h.json.inFlight, 0);
    if ("openStreams" in h.json) assert.equal(h.json.openStreams, 0);
  } finally {
    await p.stop();
  }
});
