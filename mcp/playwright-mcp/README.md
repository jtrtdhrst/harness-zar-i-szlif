# Playwright MCP

> **Źródło tej usługi Coolify:** repo `jtrtdhrst/harness-zar-i-szlif`, UUID `9e4fzsodixl4qzzap4zg0ntp`; katalog `mcp/playwright-mcp/`; Dockerfile `mcp/playwright-mcp/Dockerfile`; implementacja: `idle-proxy.cjs`.
> Kod jest w tym folderze; bieżąca produkcyjna wersja musi być potwierdzona digestem i pozytywnym E2E.


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


## Production transport + browser E2E (2026-11-23)

- The MCP dependency is pinned by package-lock.json; npm ci and the matching
  playwright-core browser install run in the Docker build, not in an ad-hoc
  running container. Browser and MCP smokes fail the build on a missing binary.
- The backend launches with --isolated so separate MCP clients do not contend
  for the same persisted Chrome-for-Testing browser profile.
- The proxy deliberately forwards Connection: keep-alive upstream, even when
  its external client disconnects after each POST or holds an SSE stream.
  Playwright returned alternating HTTP 400/200 for upstream Connection: close.
- The service needs a PID 1 init/reaper (docker-compose.yml uses init: true)
  to avoid orphan Chromium processes exhausting the PIDs limit.
- Release verification must use initialize, tools/list, browser_navigate,
  browser_snapshot and browser_tabs in the deployed image, then repeat from
  each permitted agent's Hermes MCP identity. HTTP 200 alone, a container
  healthcheck or a direct backend test is insufficient.
