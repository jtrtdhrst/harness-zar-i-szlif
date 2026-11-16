# Playwright MCP

Playwright MCP server with the idle HTTP proxy used by Paperclip.

- Build context: this directory only.
- Image: `local/playwright-mcp:0.0.83`.
- Ports: `8932` and `8761`; both expose `/mcp`.
- Data: stateless; browser profiles are ephemeral.
- The proxy starts the MCP backend on demand and stops it after
  `IDLE_SECONDS` without traffic.

```bash
docker build -t local/playwright-mcp:0.0.83 .
docker compose up -d
timeout 2 bash -c '</dev/tcp/127.0.0.1/8932'
```

The image is based on the official Microsoft Playwright image; Chromium and
its system dependencies are already included.

## Backend lifecycle contract

The proxy owns the MCP backend process and may stop it only when nothing is
using it. A client session holds real browser state, so:

- the idle watcher stops the backend only when `inFlight == 0` **and**
  `openStreams == 0` (no request being proxied, no client-held SSE channel);
- the proxy imposes **no timeout of its own on a `GET`/`DELETE` stream**. A
  client-held SSE channel may legitimately carry no bytes for minutes (the
  server simply has no event to send), so only `POST` is bounded, by
  `REQUEST_TIMEOUT_MS` (default `120000`, env-overridable for tests). A
  stream that was cut by the proxy used to drop `openStreams` to 0, which then
  let the idle watcher stop a backend whose browser context was still in use;
- a failed proxy request is returned to that one client and never tears the
  backend down — a single dropped socket must not reset every other client's
  browser context to `about:blank`;
- `/healthz` reports `backend`, `idleSeconds`, `inFlight` and `openStreams`
  for live diagnostics.

If the backend process itself exits, `backend` is cleared and the next request
spawns a fresh one; that is the only path that discards sessions.

`BACKEND_ENTRY` (default `/app/cli.js`) exists so the lifecycle regression
suite can drive a stub backend. Do not change it in production.

```bash
npm test           # lifecycle regression suite (stub backend, no Chromium)
```

## Ephemeral profiles and process-group shutdown

The MCP backend runs with `--isolated`: each browser profile is in memory, not a persistent shared folder. The child is spawned as its own process-group leader, so `killTree` reaches Chromium descendants when the proxy stops an idle backend. This prevents profile-lock collisions on restart. The module is importable for tests without binding ports; `startServers` executes only at the CLI entry point. These guarantees complement the in-flight request and SSE lifecycle protections above.

Run `npm test` for both the existing stream-lifecycle tests and the profile/process-group regression suite.
