# Hermes Gateway and Repowise multi-repo integration — evidence 2026-11-09

**Sources:** Product `miloszspyrka-code/zar-i-szlif`; Harness `miloszspyrka-code/harness-zar-i-szlif`. Paperclip Wiki migration merged as Product PR #164 and Harness PR #78 (30 + 78 historical source pages, verified manifests). Historical pages must not be mistaken for active agent policies.

## Production runtime and evidence
- Repowise 0.60.1: Coolify project `repowise-knowledge`; app UUID `oea9obpkhzbgkmipxwqmz2hj`.
- Internal MCP `http://repowise-mcp:7338/mcp` (service `lecwi3emh9hjxirn07pshmd2b51` is NOT its ID; the actual MCP service is `lecwi3emh9hjxir7gphmalie`). Sixteen read tools; unauthenticated requests rejected HTTP 401. Do not publish publicly.
- Production Hermes Gateway UUID `2sganhxhhnioiqh4an9g2f4k`, version 0.22.5, shares private `coolify` Docker network.
- All 14 Hermes profile configs contain native `mcp_servers.repowise` with profile environment secret indirection and include `repowise` in the API toolset selection. Native `hermes mcp test repowise` passed **14/14**, discovered 16 tools per profile.
- A genuine Hermes model turn in profile `harness-engineer` used Repowise `list_repos` and correctly returned Product `81c4b068` and Harness `0d19ac32`. OpenCode/DeepSeek v4.1 Flash independently used the same Repowise MCP with both repositories. This proves Hermes runtime integration, **not an external authenticated Gateway REST-triggered job**.
- Repo index SHA observed: Product `81c4b068b89f4c035098c6c9107f755f56919a87`; Harness `0d19ac3221a05a16e9f7b8a4a4fb57c3911da8a4`. SHA is a dated observation and must be checked again.

## GitHub App sync
- Existing OpenCode GitHub App credential helper and rotation timer `opencode-github-token-sync.timer`; private mirrors `/home/opencode/projects/repowise-mirrors/{product,harness}.git`.
- Enabled systemd `repowise-github-sync.timer` checks ~every 15 minutes and invokes `repowise-github-sync.service` / `/opt/repowise-knowledge/sync-from-github.sh`. It fetches both `main` branches, updates local replicas, executes native `repowise update --workspace --index-only`, validates fresh indexes, and restarts MCP if changed. There is no permanent PAT or write to upstream repositories.
- E2E changed-SHA simulation passed: isolated source replicas deliberately reverted to prior commits `98cd0581` and `fe2839d7`, then the timer service restored them to `81c4b068` / `0d19ac32`, rebuilt the indexes and restarted MCP (`SYNC_SUCCESS`).
- Verify `repowise status --workspace --format json`, MCP `list_repos`, real GitHub SHA, `journalctl -u repowise-github-sync.service`. A GitHub merge alone does not prove deployment.

## Limitations and safety
- Original cross-repo graph had 10 nodes and 3 heuristic edges, including generic `/health` / OAuth-discovery matches. They do not prove actual service dependencies; validate provider and consumer code plus deployed config.
- A distinct authenticated Gateway REST API-triggered run was not established. Do not claim it passed.
- Repowise MCP credential is shared across allowed Hermes profiles; independent per-agent authorization scopes are not proven.
- Legacy Paperclip remains read-only. Never place credentials or user data into indexed documents or logs.
