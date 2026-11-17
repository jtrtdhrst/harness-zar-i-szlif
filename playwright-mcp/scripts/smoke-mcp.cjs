// Runtime smoke for the shipped entrypoint: idle proxy -> MCP backend -> Chromium.
//
// This is the path production traffic takes. It proves the image can serve a
// real browser tool call, not just that its dependencies installed:
//   /healthz 200 -> initialize -> tools/list -> tools/call browser_navigate
// and it fails closed (non-zero exit) on any missing piece.
//
// Used in `docker build`, and against a live container after a deploy:
//   docker run --rm --entrypoint node <image> /app/scripts/smoke-mcp.cjs
// Locally: SMOKE_BACKEND_ENTRY=./node_modules/@playwright/mcp/cli.js node scripts/smoke-mcp.cjs
//
// Two rules this file must keep:
//
// 1. A passing result means a real page was returned. HTTP 200 alone proves
//    nothing, and neither does the requested title appearing anywhere in the
//    payload: the data URL we ask for contains `<title>playwright-mcp-smoke`, and
//    a failed launch echoes that URL back
//      `### Error ... expected executable at /ms-playwright/... for
//       data:text/html,<title>playwright-mcp-smoke</title>`
//    so substring matching produced a false pass. We reject `result.isError`,
//    reject an `### Error` payload, and require the exact snapshot lines
//    `- Page URL: <requested url>` and `- Page Title: <title>` inside a
//    `### Page` / `### Snapshot` block.
// 2. No `process.exit()` on any path: failures throw, the `finally` stops the
//    proxy (which kills the backend and its Chromium), closed ports are
//    verified, and only then is the exit code set. An open proxy or backend port
//    after the run is itself a failure (`ORPHAN_PROCESS`).
//
// SMOKE_LISTEN_PORT pins the proxy port (tests), SMOKE_BOOT_TIMEOUT_MS bounds boot.
const { spawn } = require("node:child_process");
const { createServer, request } = require("node:http");
const { connect } = require("node:net");
const { once } = require("node:events");
const path = require("node:path");

const PROXY = path.join(__dirname, "..", "idle-proxy.cjs");
const BACKEND_ENTRY = process.env.SMOKE_BACKEND_ENTRY || "/app/cli.js";
const BOOT_TIMEOUT_MS = Number(process.env.SMOKE_BOOT_TIMEOUT_MS || 180000);
const PAGE_TITLE = process.env.SMOKE_EXPECT_TITLE || "playwright-mcp-smoke";
const PINNED_PORT = Number(process.env.SMOKE_LISTEN_PORT || 0);

class SmokeFailure extends Error {
  constructor(code, detail) {
    super(detail);
    this.code = code;
    this.detail = detail;
  }
}
const fail = (code, detail) => { throw new SmokeFailure(code, detail); };
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

function portOpen(port, timeoutMs = 800) {
  return new Promise((resolve) => {
    const socket = connect({ host: "127.0.0.1", port });
    const done = (open) => { socket.destroy(); resolve(open); };
    socket.setTimeout(timeoutMs, () => done(false));
    socket.once("connect", () => done(true));
    socket.once("error", () => done(false));
  });
}

// The MCP streamable-HTTP transport may answer as plain JSON or as an SSE frame
// (`event: message\ndata: {...}`). Both must parse.
function parseBody(text) {
  const trimmed = String(text || "").trim();
  try {
    return JSON.parse(trimmed);
  } catch { /* fall through to SSE */ }
  for (const line of trimmed.split(/\r?\n/)) {
    if (!line.startsWith("data:")) continue;
    const payload = line.slice(5).trim();
    if (!payload) continue;
    try { return JSON.parse(payload); } catch { /* keep looking */ }
  }
  return null;
}

function post(port, body, sid) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const headers = { "content-type": "application/json", accept: "application/json, text/event-stream",
      "content-length": Buffer.byteLength(payload) };
    if (sid) headers["mcp-session-id"] = sid;
    const req = request({ host: "127.0.0.1", port, path: "/mcp", method: "POST", headers, timeout: 120000 }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, text: Buffer.concat(chunks).toString() }));
    });
    req.on("timeout", () => req.destroy(new Error("request timeout")));
    req.on("error", reject);
    req.end(payload);
  });
}

function get(port, urlPath) {
  return new Promise((resolve, reject) => {
    const req = request({ host: "127.0.0.1", port, path: urlPath, method: "GET", timeout: 10000 }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve({ status: res.statusCode, text: Buffer.concat(chunks).toString() }));
    });
    req.on("timeout", () => req.destroy(new Error("healthz timeout")));
    req.on("error", reject);
    req.end();
  });
}

// A successful browser_navigate result: not an error, and carrying the exact
// page URL/title lines of a real snapshot.
function validateBrowserResult(response, requestedUrl) {
  if (response.status !== 200) {
    fail("TOOL_CALL_HTTP", `tools/call returned HTTP ${response.status}: ${String(response.text).slice(0, 500)}`);
  }
  const body = parseBody(response.text);
  if (!body) fail("TOOL_CALL_UNPARSEABLE", `tools/call body was not JSON or SSE: ${String(response.text).slice(0, 400)}`);
  if (body.error) fail("TOOL_CALL_RPC_ERROR", `tools/call returned a JSON-RPC error: ${JSON.stringify(body.error).slice(0, 400)}`);
  const result = body.result || {};
  if (result.isError === true) {
    fail("TOOL_CALL_IS_ERROR", `tools/call reported isError=true: ${JSON.stringify(result.content || result).slice(0, 600)}`);
  }
  const content = Array.isArray(result.content) ? result.content : [];
  const text = content.filter((c) => c && c.type === "text" && typeof c.text === "string").map((c) => c.text).join("\n");
  if (!text) fail("TOOL_CALL_NO_CONTENT", `tools/call returned no text content: ${JSON.stringify(result).slice(0, 400)}`);
  if (/^###\s*Error\b/m.test(text) || /\bisError\b/.test(text)) {
    fail("TOOL_CALL_ERROR_PAYLOAD", `tools/call returned an error payload: ${text.slice(0, 600)}`);
  }
  if (!/^###\s*Page\b/m.test(text)) fail("SNAPSHOT_MISSING", `result has no "### Page" section: ${text.slice(0, 600)}`);
  if (!/^###\s*Snapshot\b/m.test(text)) fail("SNAPSHOT_MISSING", `result has no "### Snapshot" section: ${text.slice(0, 600)}`);

  const lineValue = (label) => {
    const m = text.match(new RegExp(`^-\\s*${label}:\\s*(.+)$`, "m"));
    return m ? m[1].trim() : null;
  };
  const pageUrl = lineValue("Page URL");
  const pageTitle = lineValue("Page Title");
  if (!pageUrl) fail("SNAPSHOT_INVALID", `snapshot has no "- Page URL:" line: ${text.slice(0, 600)}`);
  if (!pageTitle) fail("SNAPSHOT_INVALID", `snapshot has no "- Page Title:" line: ${text.slice(0, 600)}`);
  if (pageTitle !== PAGE_TITLE) {
    fail("SNAPSHOT_TITLE_MISMATCH", `snapshot title "${pageTitle}" is not the expected "${PAGE_TITLE}"`);
  }
  if (pageUrl !== requestedUrl) {
    fail("SNAPSHOT_URL_MISMATCH", `snapshot url "${pageUrl}" is not the requested url "${requestedUrl}"`);
  }
  const snapshotLine = (text.match(/^-\s*\[Snapshot\].*$/m) || [null])[0];
  return { pageUrl, pageTitle, snapshotLine, text };
}

async function run(ctx) {
  ctx.port = PINNED_PORT || await freePort();
  const t0 = Date.now();
  ctx.proxy = spawn(process.execPath, [PROXY], {
    env: { ...process.env, LISTEN_PORTS: String(ctx.port), IDLE_SECONDS: "600", BACKEND_ENTRY },
    stdio: ["ignore", "pipe", "pipe"],
  });
  ctx.proxy.stderr.on("data", (d) => {
    ctx.logs += String(d);
    const m = String(d).match(/Listening on http:\/\/[^:]+:(\d+)/);
    if (m) ctx.backendPort = Number(m[1]);
  });
  ctx.proxy.stdout.on("data", (d) => { ctx.logs += String(d); });
  ctx.proxy.on("exit", (code, sig) => { ctx.exited = { code, sig }; });

  // 1. the shipped entrypoint must serve its diagnostics endpoint
  let health = null;
  while (Date.now() - t0 < BOOT_TIMEOUT_MS) {
    if (ctx.exited) fail("PROXY_EXITED", `idle proxy exited during boot (${JSON.stringify(ctx.exited)}): ${ctx.logs.slice(-1500)}`);
    try {
      const r = await get(ctx.port, "/healthz");
      if (r.status === 200) { health = JSON.parse(r.text); break; }
    } catch { /* not listening yet */ }
    await sleep(300);
  }
  if (!health) fail("HEALTHZ_TIMEOUT", `/healthz did not answer within ${BOOT_TIMEOUT_MS}ms: ${ctx.logs.slice(-1500)}`);

  // 2. real MCP handshake through the proxy (backend is spawned on demand)
  const init = await post(ctx.port, { jsonrpc: "2.0", id: 1, method: "initialize",
    params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "image-smoke", version: "1.0.0" } } });
  if (init.status !== 200) fail("INITIALIZE_FAILED", `initialize returned ${init.status}: ${init.text.slice(0, 600)}`);
  const sid = init.headers["mcp-session-id"];
  if (!sid) fail("NO_SESSION", "initialize returned no mcp-session-id");
  // best effort, exactly as a real client does; the backend may answer 400
  await post(ctx.port, { jsonrpc: "2.0", method: "notifications/initialized" }, sid).catch(() => {});

  const list = await post(ctx.port, { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} }, sid);
  const listed = parseBody(list.text);
  const tools = (listed && listed.result && listed.result.tools) || [];
  const names = tools.map((t) => t.name);
  if (!names.includes("browser_navigate")) {
    fail("TOOLS_MISSING", `tools/list returned ${names.length} tools without browser_navigate: ${names.slice(0, 20).join(",")}`);
  }

  // 3. force an actual Chromium launch through the MCP backend
  const url = `data:text/html,<title>${PAGE_TITLE}</title><p id=v>1</p>`;
  const nav = await post(ctx.port, { jsonrpc: "2.0", id: 3, method: "tools/call",
    params: { name: "browser_navigate", arguments: { url } } }, sid);
  const snapshot = validateBrowserResult(nav, url);

  const after = JSON.parse((await get(ctx.port, "/healthz")).text);
  if (!after.backend) fail("BACKEND_NOT_RUNNING", `/healthz reports backend=${after.backend} after a successful call`);

  return {
    check: "mcp-idle-proxy-browser",
    entrypoint: PROXY,
    backendEntry: BACKEND_ENTRY,
    port: ctx.port,
    backendPort: ctx.backendPort,
    bootMs: Date.now() - t0,
    toolCount: names.length,
    toolUsed: "browser_navigate",
    pageUrl: snapshot.pageUrl,
    pageTitle: snapshot.pageTitle,
    snapshotLine: snapshot.snapshotLine,
    healthz: after,
  };
}

// Always runs. Stops the proxy, which sends SIGTERM/SIGKILL to the backend
// process group (and therefore Chromium), then proves both ports are closed.
async function cleanup(ctx) {
  const report = { proxyExited: !!ctx.exited, proxyPort: ctx.port, backendPort: ctx.backendPort,
    proxyPortClosed: false, backendPortClosed: null };
  if (ctx.proxy && !ctx.exited) {
    ctx.proxy.kill("SIGTERM");
    const deadline = Date.now() + 15000;
    while (!ctx.exited && Date.now() < deadline) await sleep(200);
    if (!ctx.exited) {
      ctx.proxy.kill("SIGKILL");
      const hard = Date.now() + 5000;
      while (!ctx.exited && Date.now() < hard) await sleep(100);
    }
  }
  report.proxyExited = !!ctx.exited;
  for (let i = 0; i < 25 && await portOpen(ctx.port); i++) await sleep(200);
  report.proxyPortClosed = !(await portOpen(ctx.port));
  if (ctx.backendPort) {
    for (let i = 0; i < 25 && await portOpen(ctx.backendPort); i++) await sleep(200);
    report.backendPortClosed = !(await portOpen(ctx.backendPort));
  }
  return report;
}

(async () => {
  const ctx = { proxy: null, port: null, backendPort: null, exited: null, logs: "" };
  let outcome = null;
  let failure = null;
  try {
    outcome = await run(ctx);
  } catch (e) {
    failure = e instanceof SmokeFailure ? e : new SmokeFailure("SMOKE_ERROR", String((e && e.message) || e));
  } finally {
    ctx.cleanup = await cleanup(ctx);
  }
  // An open port after cleanup means we leaked a process: never a clean run.
  const orphans = [];
  if (!ctx.cleanup.proxyPortClosed) orphans.push(`proxy port ${ctx.cleanup.proxyPort}`);
  if (ctx.cleanup.backendPortClosed === false) orphans.push(`backend port ${ctx.cleanup.backendPort}`);

  const base = { entrypoint: PROXY, backendEntry: BACKEND_ENTRY, cleanup: ctx.cleanup };
  if (!failure && orphans.length) {
    failure = new SmokeFailure("ORPHAN_PROCESS", `still listening after cleanup: ${orphans.join(", ")}`);
  }
  if (failure) {
    console.error(JSON.stringify({ ok: false, code: failure.code, detail: failure.detail, ...base,
      logs: ctx.logs.slice(-1500) }, null, 2));
    process.exitCode = 1;
    return;
  }
  console.log(JSON.stringify({ ok: true, ...outcome, ...base }, null, 2));
  process.exitCode = 0;
})();
