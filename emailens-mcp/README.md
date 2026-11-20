# Emailens MCP

Persistent HTTP bridge for the Emailens stdio MCP server.

- Build context: this directory only.
- Image: `local/emailens-mcp:0.10.0` (override with `IMAGE`).
- Port: `3100`, MCP path `/mcp`, health `GET /healthz`.
- Required secret: `EMAILENS_BRIDGE_TOKEN`.
- Data: stateless; no application data is stored in this project.

```bash
cp .env.example .env   # set EMAILENS_BRIDGE_TOKEN
docker build -t local/emailens-mcp:0.10.0 .
docker compose up -d
curl -fsS http://127.0.0.1:3100/healthz
```

The bridge keeps one Emailens child process alive, restarts it on demand and drops
it after `IDLE_SECONDS` without traffic.

## Deployment (Harness auto-main)

A merge to `miloszspyrka-code/harness-zar-i-szlif` `main` that touches this
directory is built and promoted by the existing `harness-image-delivery.timer`
(`--auto-main`): exact main SHA, immutable local digest, Coolify service
`16qnapdkj0qqqmeokepdechk`, live health readback and one rollback. No per-release
request/grant or operator source pin is required for this service.
