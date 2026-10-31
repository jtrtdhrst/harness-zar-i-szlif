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
