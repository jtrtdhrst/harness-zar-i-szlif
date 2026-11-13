// Minimal streamable-HTTP MCP backend used only by the idle-proxy regression
// suite. It models the two things the proxy must not destroy implicitly:
//   * a per-session browser context (surfaced as `state`: pid + url)
//   * a backend process identity (a restart shows up as a different pid)
//
// Tools: state, navigate{url}, boom (drops the socket mid-request), slow{ms}.
import { createServer } from "node:http";
import { appendFileSync } from "node:fs";
import { randomUUID } from "node:crypto";

const argv = process.argv.slice(2);
const argOf = (name, fallback) => {
  const i = argv.indexOf(name);
  return i >= 0 && argv[i + 1] !== undefined ? argv[i + 1] : fallback;
};
const port = Number(argOf("--port", "0"));
const host = argOf("--host", "127.0.0.1");

if (process.env.STUB_STARTS_FILE) {
  try {
    appendFileSync(process.env.STUB_STARTS_FILE, `${process.pid}\n`);
  } catch {
    /* evidence file is best-effort */
  }
}

const sessions = new Map(); // sid -> { url }
const tools = [
  { name: "state", description: "backend pid + session browser url" },
  { name: "navigate", description: "set browser url", inputSchema: { type: "object" } },
  { name: "boom", description: "drop the socket without a response" },
  { name: "slow", description: "respond after N ms", inputSchema: { type: "object" } },
];

const json = (res, status, body, extraHeaders = {}) => {
  const payload = Buffer.from(JSON.stringify(body));
  res.writeHead(status, {
    "content-type": "application/json",
    "content-length": payload.length,
    ...extraHeaders,
  });
  res.end(payload);
};

const rpcError = (res, status, id, message) =>
  json(res, status, { jsonrpc: "2.0", id: id ?? null, error: { code: -32000, message } });

async function readBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  return Buffer.concat(chunks).toString("utf8");
}

async function handlePost(req, res) {
  let msg;
  try {
    msg = JSON.parse((await readBody(req)) || "{}");
  } catch {
    return json(res, 400, { error: "bad json" });
  }
  if (msg.method === "initialize") {
    const sid = randomUUID();
    sessions.set(sid, { url: "about:blank" });
    return json(
      res,
      200,
      {
        jsonrpc: "2.0",
        id: msg.id,
        result: {
          protocolVersion: "2025-06-18",
          capabilities: { tools: {} },
          serverInfo: { name: "stub-playwright-mcp", version: "1.0.0" },
        },
      },
      { "mcp-session-id": sid },
    );
  }
  if (msg.method === "notifications/initialized") {
    res.writeHead(202).end();
    return;
  }
  const sid = req.headers["mcp-session-id"];
  const session = sid ? sessions.get(String(sid)) : undefined;
  if (!session) return rpcError(res, 404, msg.id, "Session not found");

  if (msg.method === "tools/list") {
    return json(res, 200, { jsonrpc: "2.0", id: msg.id, result: { tools } });
  }
  if (msg.method !== "tools/call") {
    return rpcError(res, 400, msg.id, `unknown method ${msg.method}`);
  }
  const name = msg.params?.name;
  const args = msg.params?.arguments ?? {};
  if (name === "boom") {
    req.socket.destroy();
    return;
  }
  if (name === "slow") {
    await new Promise((r) => setTimeout(r, Number(args.ms ?? 0)));
  }
  if (name === "navigate") session.url = String(args.url ?? "about:blank");
  const value =
    name === "state"
      ? { pid: process.pid, sessionId: String(sid), url: session.url }
      : { ok: true, pid: process.pid, url: session.url };
  return json(res, 200, {
    jsonrpc: "2.0",
    id: msg.id,
    result: { content: [{ type: "text", text: JSON.stringify(value) }] },
  });
}

function handleGet(req, res) {
  const sid = req.headers["mcp-session-id"];
  if (!sid || !sessions.has(String(sid))) return rpcError(res, 404, null, "Session not found");
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  res.write(`: stub stream ${String(sid).slice(0, 8)}\n\n`);
  const keepAlive = setInterval(() => res.write(": keepalive\n\n"), 2000);
  req.on("close", () => {
    clearInterval(keepAlive);
    res.end();
  });
}

const server = createServer((req, res) => {
  const path = new URL(req.url ?? "/", "http://x").pathname;
  if (path !== "/mcp") return json(res, 404, { error: "not found" });
  if (req.method === "POST") {
    handlePost(req, res).catch(() => {
      if (!res.headersSent) json(res, 500, { error: "internal" });
    });
    return;
  }
  if (req.method === "GET") return handleGet(req, res);
  if (req.method === "DELETE") return json(res, 200, { ok: true });
  return json(res, 405, { error: "method not allowed" });
});

server.listen(port, host, () => {
  const actual = server.address();
  // The proxy discovers the backend port from this exact line.
  process.stderr.write(`Listening on http://${host}:${actual.port}\n`);
});
