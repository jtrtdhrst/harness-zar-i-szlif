// Minimal keep-alive MCP-ish backend used by tests/backend-connection.test.mjs.
//
// It models the one property of the real @playwright/mcp backend that broke the
// proxy: the server answers with `Connection: keep-alive` and keeps a POST
// response stream per connection, so a client that reuses that socket for the
// next request gets a bare empty-body HTTP 400 instead of a JSON-RPC result.
// The stub therefore answers keep-alive regardless of the client's
// `Connection: close` header and records every accepted socket plus every
// request seen on it (CONN_LOG).
import net from "node:net";
import { appendFileSync } from "node:fs";

const logFile = process.env.CONN_LOG;
const record = (line) => { if (logFile) appendFileSync(logFile, `${line}\n`); };

const server = net.createServer((socket) => {
  const conn = String(socket.remotePort);
  record(`conn ${conn}`);
  let buf = "";
  socket.on("data", (chunk) => {
    buf += chunk.toString("latin1");
    for (;;) {
      const headEnd = buf.indexOf("\r\n\r\n");
      if (headEnd === -1) return;
      const head = buf.slice(0, headEnd);
      const lenMatch = /content-length:\s*(\d+)/i.exec(head);
      const len = lenMatch ? Number(lenMatch[1]) : 0;
      const bodyStart = headEnd + 4;
      if (buf.length < bodyStart + len) return;
      const body = buf.slice(bodyStart, bodyStart + len);
      buf = buf.slice(bodyStart + len);
      record(`req ${conn}`);
      let id = 1;
      try { id = JSON.parse(body).id ?? 1; } catch { /* notifications have no id */ }
      const payload = JSON.stringify({ jsonrpc: "2.0", id, result: { ok: true, conn } });
      socket.write(
        `HTTP/1.1 200 OK\r\n` +
        `Content-Type: application/json\r\n` +
        `Content-Length: ${Buffer.byteLength(payload)}\r\n` +
        `mcp-session-id: stub-session\r\n` +
        `Connection: keep-alive\r\n\r\n${payload}`,
      );
    }
  });
  socket.on("error", () => {});
});

server.listen(0, "127.0.0.1", () => {
  console.error(`Listening on http://127.0.0.1:${server.address().port}`);
});
