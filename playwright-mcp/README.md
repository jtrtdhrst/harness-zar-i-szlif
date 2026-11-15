# Playwright MCP

Playwright MCP server with the idle HTTP proxy used by Paperclip.

- Build context: this directory only.
- Image: `local/playwright-mcp:0.0.83`.
- Ports: `8932` and `8761`; both expose `/mcp`.
- Data: stateless; browser profiles are ephemeral.
- The proxy starts the MCP backend on demand and stops it after
  `IDLE_SECONDS` without traffic.
- The backend runs with `--isolated` (profile kept in memory, never on disk) and
  is spawned as its own process group, so the idle stop signals Chromium as well
  as the node child. Without both, a respawned backend collided with a lingering
  browser on the persistent profile, and every tool then failed with
  `Browser is already in use ... use --isolated` (browser_navigate answered a
  bare HTTP 400) until the container was restarted.

```bash
npm test   # node --test (idle-proxy.test.cjs)
```

```bash
docker build -t local/playwright-mcp:0.0.83 .
docker compose up -d
timeout 2 bash -c '</dev/tcp/127.0.0.1/8932'
```

The image is based on the official Microsoft Playwright image; Chromium and
its system dependencies are already included.
