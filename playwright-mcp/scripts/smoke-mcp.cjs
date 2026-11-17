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
const { spawn } = require("node:child_process");
const { createServer, request } = require("node:http");
const { once } = require("node:events");
const path = require("node:path");

const PROXY = path.join(__dirname, "..", "idle-proxy.cjs");
const BACKEND_ENTRY = process.env.SMOKE_BACKEND_ENTRY || "/app/cli.js";
const BOOT_TIMEOUT_MS = Number(process.env.SMOKE_BOOT_TIMEOUT_MS || 180000);
const PAGE_TITLE = "playwright-mcp-smoke";

const fail = (code, detail) => {
  console.error(JSON.stringify({ ok: false, code, detail }, null, 2));
  process.exit(1);
};
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

(async () => {
  const port = await freePort();
  const t0 = Date.now();
  const proxy = spawn(process.execPath, [PROXY], {
    env: { ...process.env, LISTEN_PORTS: String(port), IDLE_SECONDS: "600", BACKEND_ENTRY },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let logs = "";
  proxy.stderr.on("data", (d) => { logs += String(d); });
  proxy.stdout.on("data", (d) => { logs += String(d); });
  let exited = null;
  proxy.on("exit", (code, sig) => { exited = { code, sig }; });

  const stop = async () => {
    if (exited) return;
    proxy.kill("SIGTERM");
    const deadline = Date.now() + 15000;
    while (!exited && Date.now() < deadline) await sleep(200);
    if (!exited) proxy.kill("SIGKILL");
  };

  try {
    // 1. the shipped entrypoint must serve its diagnostics endpoint
    let health = null;
    while (Date.now() - t0 < BOOT_TIMEOUT_MS) {
      if (exited) fail("PROXY_EXITED", `idle proxy exited during boot (${JSON.stringify(exited)}): ${logs.slice(-1500)}`);
      try {
        const r = await get(port, "/healthz");
        if (r.status === 200) { health = JSON.parse(r.text); break; }
      } catch { /* not listening yet */ }
      await sleep(300);
    }
    if (!health) fail("HEALTHZ_TIMEOUT", `/healthz did not answer within ${BOOT_TIMEOUT_MS}ms: ${logs.slice(-1500)}`);

    // 2. real MCP handshake through the proxy (backend is spawned on demand)
    const init = await post(port, { jsonrpc: "2.0", id: 1, method: "initialize",
      params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "image-smoke", version: "1.0.0" } } });
    if (init.status !== 200) fail("INITIALIZE_FAILED", `initialize returned ${init.status}: ${init.text.slice(0, 600)}`);
    const sid = init.headers["mcp-session-id"];
    if (!sid) fail("NO_SESSION", "initialize returned no mcp-session-id");
    // best effort, exactly as a real client does; the backend may answer 400
    await post(port, { jsonrpc: "2.0", method: "notifications/initialized" }, sid).catch(() => {});

    const list = await post(port, { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} }, sid);
    const listed = parseBody(list.text);
    const tools = (listed && listed.result && listed.result.tools) || [];
    const names = tools.map((t) => t.name);
    if (!names.includes("browser_navigate")) {
      fail("TOOLS_MISSING", `tools/list returned ${names.length} tools without browser_navigate: ${names.slice(0, 20).join(",")}`);
    }

    // 3. force an actual Chromium launch through the MCP backend
    const url = `data:text/html,<title>${PAGE_TITLE}</title><p id=v>1</p>`;
    const nav = await post(port, { jsonrpc: "2.0", id: 3, method: "tools/call",
      params: { name: "browser_navigate", arguments: { url } } }, sid);
    const navBody = parseBody(nav.text);
    const navText = JSON.stringify((navBody && navBody.result) || nav.text);
    if (nav.status !== 200 || !navText.includes(PAGE_TITLE)) {
      fail("BROWSER_CALL_FAILED", `browser_navigate did not return the page snapshot: ${navText.slice(0, 800)}`);
    }

    const after = JSON.parse((await get(port, "/healthz")).text);
    if (!after.backend) fail("BACKEND_NOT_RUNNING", `/healthz reports backend=${after.backend} after a successful call`);

    console.log(JSON.stringify({
      ok: true,
      check: "mcp-idle-proxy-browser",
      entrypoint: PROXY,
      backendEntry: BACKEND_ENTRY,
      port,
      bootMs: Date.now() - t0,
      toolCount: names.length,
      toolUsed: "browser_navigate",
      browserSnapshot: navText.slice(0, 300),
      healthz: after,
    }, null, 2));
  } catch (e) {
    fail("SMOKE_ERROR", `${String((e && e.message) || e)} | logs: ${logs.slice(-1500)}`);
  } finally {
    await stop();
  }
})();
