// Playwright MCP idle proxy: serves LISTEN_PORTS, spawns the real MCP server
// on 127.0.0.1:8933 on demand, kills it after IDLE_SECONDS without traffic.
// Session-less clients (Paperclip Apps check: bare tools/list) get a shared
// backend session created on their behalf. Logs to stderr only.
const http = require("http");
const { spawn } = require("child_process");

const IDLE_SECONDS = (() => {
  const v = parseInt(process.env.IDLE_SECONDS || "600", 10);
  return Number.isFinite(v) && v >= 10 ? v : 600; // cannot be disabled, min 10s (tests)
})();
const LISTEN_PORTS = (process.env.LISTEN_PORTS || "8932,8761").split(",").map((s) => Number(s.trim())).filter(Boolean);
// Entry point of the real MCP server. Overridable only so the lifecycle
// regression suite can drive a stub backend; the shipped default is unchanged.
const BACKEND_ENTRY = process.env.BACKEND_ENTRY || "/app/cli.js";
const BACKEND_ARGS = ["--headless", "--browser", "chromium", "--no-sandbox",
  "--port", "0", "--host", "127.0.0.1", "--allowed-hosts", "*"];

const log = (...a) => console.error("[proxy]", ...a);

let backend = null;      // { child, port } while running
let sharedSid = null;    // backend session for session-less clients
let lastActive = Date.now();
let starting = null;     // queued callbacks while backend boots
let closing = false;
let inFlight = 0;        // MCP requests currently proxied to the backend
let openStreams = 0;     // client-held GET/DELETE channels (SSE)

// A request in flight, or a client-held stream, means the session is in use:
// tearing the backend down underneath it destroys live browser state.
const busy = () => inFlight > 0 || openStreams > 0;

const touch = () => { lastActive = Date.now(); };

function markDead(code, sig) {
  if (backend) log(`backend exited code=${code} sig=${sig}`);
  backend = null;
  sharedSid = null;
}

function spawnBackend() {
  // Random port per spawn (--port 0): no EADDRINUSE races with a previous
  // backend that is still shutting down. Port discovered from stderr.
  const child = spawn("node", [BACKEND_ENTRY, ...BACKEND_ARGS], { stdio: ["ignore", "pipe", "pipe"] });
  let port = 0;
  child.stderr.on("data", (d) => {
    process.stderr.write(`[pw] ${d}`);
    const m = String(d).match(/Listening on http:\/\/[^:]+:(\d+)/);
    if (m) port = Number(m[1]);
  });
  child.on("exit", (c, s) => { if (!closing) markDead(c, s); });
  return { child, get port() { return port; } };
}

function backendRequest(be, options, body, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: "127.0.0.1", port: be.port, timeout: timeoutMs, ...options }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks) }));
    });
    req.on("timeout", () => { req.destroy(new Error("backend timeout")); });
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

async function backendInitialize(be) {
  const payload = JSON.stringify({ jsonrpc: "2.0", id: "proxy-shared-init",
    method: "initialize", params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "playwright-idle-proxy", version: "1.0.0" } } });
  const r = await backendRequest(be, { method: "POST", path: "/mcp",
    headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "content-length": Buffer.byteLength(payload) } }, payload, 60000);
  const sid = r.headers["mcp-session-id"];
  if (!sid) throw new Error("backend gave no session id");
  // best-effort initialized notification (no response body expected)
  const n = JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" });
  backendRequest(be, { method: "POST", path: "/mcp",
    headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "content-length": Buffer.byteLength(n), "mcp-session-id": sid } }, n, 15000).catch(() => {});
  return sid;
}

function ensureBackend(cb) {
  if (backend) return cb(null);
  if (starting) return starting.push(cb);
  starting = [cb];
  touch(); // a spawn counts as activity
  const be = spawnBackend();
  backend = be;
  log("spawning backend...");
  const t0 = Date.now();
  const tryInit = async () => {
    if (backend !== be) return done(new Error("backend replaced during boot"));
    if (!be.port) {
      if (Date.now() - t0 > 90000) { killBackend(); return done(new Error("backend boot timeout: no port")); }
      return setTimeout(tryInit, 500);
    }
    try {
      sharedSid = await backendInitialize(be);
      log(`backend ready in ${((Date.now() - t0) / 1000).toFixed(1)}s, shared session ${String(sharedSid).slice(0, 8)}`);
      done(null);
    } catch (e) {
      if (Date.now() - t0 > 90000) { killBackend(); return done(new Error("backend boot timeout: " + e.message)); }
      setTimeout(tryInit, 1000);
    }
  };
  const done = (err) => { const q = starting; starting = null; if (err) { if (backend === be) { backend = null; sharedSid = null; } } q.forEach((f) => f(err)); };
  setTimeout(tryInit, 1500);
}

function killBackend() {
  const be = backend;
  backend = null;
  sharedSid = null;
  if (be) {
    // SIGTERM now, SIGKILL after grace; the handle is retained so a lingerer
    // can still be reaped (no orphaned browsers holding resources).
    try { be.child.kill("SIGTERM"); } catch {}
    setTimeout(() => { try { be.child.kill("SIGKILL"); } catch {} }, 10000).unref();
  }
}

function relay(clientRes, bRes, stripSession) {
  const h = { ...bRes.headers };
  delete h["connection"]; delete h["transfer-encoding"];
  if (stripSession) delete h["mcp-session-id"];
  clientRes.writeHead(bRes.status, h);
  clientRes.end(bRes.body);
}

async function handleMcp(clientReq, clientRes, chunks) {
  const bodyRaw = Buffer.concat(chunks).toString();
  let msg = null;
  try { msg = JSON.parse(bodyRaw); } catch { clientRes.writeHead(400).end('{"error":"bad json"}'); return; }
  const sid = clientReq.headers["mcp-session-id"];
  const isInit = msg && msg.method === "initialize";
  if (isInit || sid) {
    // transparent: client owns the session
    ensureBackend((err) => {
      if (err || !backend) { clientRes.writeHead(502).end('{"error":"backend unavailable"}'); return; }
      const be = backend;
      const headers = { ...clientReq.headers, host: `127.0.0.1:${be.port}`, connection: "close" };
      delete headers["content-length"];
      inFlight++;
      let released = false;
      const release = () => { if (released) return; released = true; inFlight--; };
      const proxy = http.request({ host: "127.0.0.1", port: be.port, method: "POST", path: "/mcp", headers, timeout: 120000 },
        (bRes) => {
          const h = { ...bRes.headers };
          delete h["connection"]; delete h["transfer-encoding"];
          clientRes.writeHead(bRes.statusCode, h);
          bRes.on("end", release);
          bRes.on("close", release);
          bRes.pipe(clientRes);
        });
      proxy.on("timeout", () => { proxy.destroy(); release(); if (!clientRes.headersSent) clientRes.writeHead(504).end('{"error":"backend timeout"}'); });
      // A single failed call is isolated to that call: killing the backend here
      // would erase every other client's live browser session and force a fresh
      // process (fresh context = about:blank) on the next request. If the
      // backend actually died, its exit handler clears `backend` and the next
      // request respawns it.
      proxy.on("error", (e) => {
        release();
        log(`backend request failed: ${e.message}`);
        if (!clientRes.headersSent) clientRes.writeHead(502).end('{"error":"backend unavailable"}');
        else clientRes.end();
      });
      clientRes.on("close", release);
      proxy.end(bodyRaw);
    });
    return;
  }
  // session-less: use shared backend session
  ensureBackend(async (err) => {
    if (err || !sharedSid) { clientRes.writeHead(502).end('{"error":"backend unavailable"}'); return; }
    inFlight++;
    try {
      if (!backend) { clientRes.writeHead(502).end('{"error":"backend unavailable"}'); return; }
      const bRes = await backendRequest(backend, { method: "POST", path: "/mcp",
        headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-session-id": sharedSid } }, bodyRaw, 120000);
      relay(clientRes, bRes, true);
    } catch (e) {
      // Same isolation rule as above: one failed shared-session request must
      // not tear down the backend for every other client.
      log(`shared tools request failed: ${e.message}`);
      if (!clientRes.headersSent) clientRes.writeHead(502).end('{"error":"backend unavailable"}');
      else clientRes.end();
    } finally {
      inFlight--;
    }
  });
}

function handler(clientReq, clientRes) {
  const url = new URL(clientReq.url || "/", "http://x");
  if (url.pathname === "/healthz") {
    clientRes.writeHead(200, { "content-type": "application/json" });
    clientRes.end(JSON.stringify({ ok: true, backend: !!backend, idleSeconds: Math.round((Date.now() - lastActive) / 1000), inFlight, openStreams }));
    return;
  }
  if (url.pathname !== "/mcp") { clientRes.writeHead(404).end('{"error":"not found"}'); return; }
  if (clientReq.method === "POST") {
    touch(); // only real MCP traffic keeps the backend alive
    const chunks = [];
    let size = 0;
    clientReq.on("data", (c) => { size += c.length; if (size > 10 * 1024 * 1024) clientReq.destroy(); else chunks.push(c); });
    clientReq.on("end", () => handleMcp(clientReq, clientRes, chunks));
    return;
  }
  if (clientReq.method === "GET" || clientReq.method === "DELETE") {
    const sid = clientReq.headers["mcp-session-id"];
    if (!sid) { clientRes.writeHead(404).end('{"error":"unknown session"}'); return; }
    touch(); // an SSE channel held by a client is live session traffic
    ensureBackend((err) => {
      if (err || !backend) { clientRes.writeHead(502).end('{"error":"backend unavailable"}'); return; }
      const be = backend;
      openStreams++;
      let released = false;
      const release = () => { if (released) return; released = true; openStreams--; };
      const proxy = http.request({ host: "127.0.0.1", port: be.port, method: clientReq.method, path: "/mcp",
        headers: { ...clientReq.headers, host: `127.0.0.1:${be.port}`, connection: "close" }, timeout: 120000 },
        (bRes) => {
          const h = { ...bRes.headers }; delete h["connection"]; delete h["transfer-encoding"];
          clientRes.writeHead(bRes.statusCode, h);
          bRes.on("data", touch);
          bRes.on("end", release);
          bRes.on("close", release);
          bRes.pipe(clientRes);
        });
      proxy.on("timeout", () => { proxy.destroy(); release(); if (!clientRes.headersSent) clientRes.writeHead(504).end(); else clientRes.end(); });
      proxy.on("error", () => { release(); if (!clientRes.headersSent) clientRes.writeHead(502).end(); else clientRes.end(); });
      clientRes.on("close", release);
      proxy.end();
    });
    return;
  }
  clientRes.writeHead(405).end('{"error":"method not allowed"}');
}

for (const p of LISTEN_PORTS) {
  http.createServer(handler).listen(p, "0.0.0.0", () => log(`listening on :${p}/mcp (idle ${IDLE_SECONDS}s)`));
}

// idle watcher: kill ONLY the backend (proxy stays, respawns on demand).
// Never while a request is in flight or a client holds a stream: that would
// terminate a live MCP session and reset its browser context to about:blank.
setInterval(() => {
  if (closing || !backend || busy()) return;
  const idle = (Date.now() - lastActive) / 1000;
  if (idle > IDLE_SECONDS) {
    log(`idle ${Math.round(idle)}s > ${IDLE_SECONDS}s, stopping backend`);
    killBackend();
  }
}, 5000).unref();

function shutdown(sig) {
  if (closing) return;
  closing = true;
  log(`received ${sig}`);
  killBackend();
  setTimeout(() => process.exit(0), 500).unref();
}
process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
