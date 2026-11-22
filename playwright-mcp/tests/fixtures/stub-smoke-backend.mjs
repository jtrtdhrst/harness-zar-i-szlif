// Scripted MCP backend for the smoke failure-path tests.
//
// The production defect this models: a browser launch failure comes back as a
// tool call that echoes the requested data URL (which itself contains
// `<title>playwright-mcp-smoke`), so a smoke that only substring-matches the
// title passes on a failed launch. Modes:
//
//   success                  real-shaped snapshot (positive control)
//   error-echo-url           isError=true, message echoes the requested URL/title
//   error-with-fake-snapshot isError=true but the error text is a well-formed
//                            snapshot, so only the isError gate can reject it
//   wrong-title              no error, snapshot with a different page title
//
// It listens on an ephemeral port, prints `Listening on http://127.0.0.1:<port>`
// for the idle proxy, hands out an `mcp-session-id`, and writes its own pid to
// SMOKE_STUB_PID_FILE so a test can prove it was reaped.
import http from "node:http";
import { writeFileSync } from "node:fs";

const MODE = process.env.SMOKE_STUB_MODE || "success";
const TITLE = process.env.SMOKE_EXPECT_TITLE || "playwright-mcp-smoke";
const pidFile = process.env.SMOKE_STUB_PID_FILE;
if (pidFile) writeFileSync(pidFile, String(process.pid));

const snapshotText = (title) => [
  "### Ran Playwright code",
  "```js",
  `await page.goto('data:text/html,<title>${title}</title><p id=v>1</p>');`,
  "```",
  "### Page",
  `- Page URL: data:text/html,<title>${title}</title><p id=v>1</p>`,
  `- Page Title: ${title}`,
  "### Snapshot",
  "- [Snapshot](.playwright-mcp/page-stub.yml)",
].join("\n");

function toolResult(url) {
  switch (MODE) {
    case "error-echo-url":
      return { isError: true, content: [{ type: "text", text:
        `### Error\nError: Browser "chrome-for-testing" is not installed; expected executable at ` +
        `/ms-playwright/chromium-1247/chrome-linux64/chrome for ${url}` }] };
    case "error-with-fake-snapshot":
      return { isError: true, content: [{ type: "text", text: `### Error\nError: launch failed\n\n${snapshotText(TITLE)}` }] };
    case "wrong-title":
      return { content: [{ type: "text", text: snapshotText("some-other-page") }] };
    case "success":
    default:
      return { content: [{ type: "text", text: snapshotText(TITLE) }] };
  }
}

const server = http.createServer((req, res) => {
  const chunks = [];
  req.on("data", (c) => chunks.push(c));
  req.on("end", () => {
    const raw = Buffer.concat(chunks).toString();
    let msg = {};
    try { msg = JSON.parse(raw); } catch { /* notifications may be empty */ }
    const reply = (id, result, extraHeaders = {}) => {
      const body = JSON.stringify({ jsonrpc: "2.0", id, result });
      res.writeHead(200, { "content-type": "application/json", "content-length": Buffer.byteLength(body),
        "mcp-session-id": "stub-session", ...extraHeaders });
      res.end(body);
    };

    if (msg.method === "initialize") {
      reply(msg.id, { protocolVersion: "2025-06-18", capabilities: { tools: {} },
        serverInfo: { name: "stub-backend", version: "0.0.0" } });
      return;
    }
    if (msg.method === "notifications/initialized") {
      res.writeHead(202).end();
      return;
    }
    if (msg.method === "tools/list") {
      reply(msg.id, { tools: [{ name: "browser_navigate", description: "stub navigate",
        inputSchema: { type: "object", properties: { url: { type: "string" } } } }] });
      return;
    }
    if (msg.method === "tools/call") {
      reply(msg.id, toolResult(msg.params && msg.params.arguments && msg.params.arguments.url));
      return;
    }
    reply(msg.id, {});
  });
});

server.listen(0, "127.0.0.1", () => {
  console.error(`Listening on http://127.0.0.1:${server.address().port}`);
});

process.on("SIGTERM", () => { server.close(() => process.exit(0)); });
