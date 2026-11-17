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

The image is based on the official Microsoft Playwright image, which supplies
the OS libraries Chromium needs. It does **not** supply the browser build that
this image runs — see below.

## Browser/Playwright version pairing (hard contract)

`package-lock.json` decides which Playwright build runs, and that build launches
one exact Chromium revision. The base image only carries the browsers of its own
release. The two must be reconciled explicitly:

| what | value |
| --- | --- |
| `@playwright/mcp` | pinned exactly in `package.json` + lockfile |
| Playwright build | pinned exactly by `@playwright/mcp` (an alpha stamp) |
| required Chromium | the revision in that build's `browsers.json` |
| base image | `mcr.microsoft.com/playwright:v1.64.1-noble` (deps only) |

On 2026-11-17 the image was built on `v1.57.0-noble` (Chromium revision 1200)
while `@playwright/mcp 0.0.83` requires revision 1247, and
`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` prevented the missing build from ever being
installed. Every browser call failed with:

```
browserType.launch: Executable doesn't exist at
/ms-playwright/chromium_headless_shell-1247/...
```

Rules that keep this from recurring:

- dependencies install from the lockfile only (`npm ci`, never `npm install`);
- the pinned Chromium build is installed at build time
  (`playwright-core/cli.js install chromium chromium-headless-shell`) unless the
  base image is on exactly the pinned Playwright release;
- `scripts/check-browser-pairing.cjs` fails on any configuration that breaks
  those rules, and `tests/browser-pairing.test.mjs` re-runs the pre-fix
  Dockerfile as a negative control.

## Build and runtime smokes

`docker build` fails unless Chromium really launches and the shipped entrypoint
serves a real browser call:

```bash
node scripts/smoke-chromium.cjs   # pinned browser exists, launches, runs script
node scripts/smoke-mcp.cjs        # idle proxy -> MCP backend -> browser_navigate
bash scripts/docker-smoke.sh      # both, inside the built image
```

`smoke-mcp.cjs` drives the production path end to end: `/healthz`, MCP
`initialize`, `tools/list`, then `tools/call browser_navigate` and a page
snapshot. Point it at a live container with
`docker run --rm --entrypoint node <image> /app/scripts/smoke-mcp.cjs`.
Locally, set `SMOKE_BACKEND_ENTRY=./node_modules/@playwright/mcp/cli.js`.

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
- every outbound request to the backend uses its own socket (`agent: false`).
  The backend keeps a POST response stream per connection, so reusing a
  keep-alive socket made every second call on a session fail with a bare
  empty-body `400` (and `GET /mcp` answer `400`). Measured before the fix:
  `200/400/200/400` for four identical calls; after: `200/200/200/200`.
  `tests/backend-connection.test.mjs` asserts one socket per call and re-runs
  the scenario against a reusing proxy as its negative control;
- `/healthz` reports `backend`, `idleSeconds`, `inFlight` and `openStreams`
  for live diagnostics.

If the backend process itself exits, `backend` is cleared and the next request
spawns a fresh one; that is the only path that discards sessions.

`BACKEND_ENTRY` (default `/app/cli.js`) exists so the lifecycle regression
suite can drive a stub backend. Do not change it in production.

```bash
npm test           # lifecycle + connection + version-pairing suites (no Chromium)
npm run smoke:chromium   # needs installed dependencies and browsers
npm run smoke:mcp        # needs installed dependencies and browsers
```

## Ephemeral profiles and process-group shutdown

The MCP backend runs with `--isolated`: each browser profile is in memory, not a persistent shared folder. The child is spawned as its own process-group leader, so `killTree` reaches Chromium descendants when the proxy stops an idle backend. This prevents profile-lock collisions on restart. The module is importable for tests without binding ports; `startServers` executes only at the CLI entry point. These guarantees complement the in-flight request and SSE lifecycle protections above.

Run `npm test` for the stream-lifecycle, backend-connection and version-pairing suites.
