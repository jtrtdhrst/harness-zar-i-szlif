# Repowise E2E acceptance log (snapshot 2026-11-09)

- Installed: Repowise v0.60.1, Coolify project `repowise-knowledge`.
- API app: `oea9obpkhzbgkmipxwqmz2hj`; internal API HTTP 200 and dashboard HTTP 200.
- MCP service: `lecwi3emh9hjxir7gphmalie`, internal only at `http://repowise-mcp:7338/mcp`.
- Verified: MCP initialize 200; tools/list 200; list_repos 200; get_architecture 200; negative bearer checks 401; repo indexes persist through service restart.
- Repo SHA provenance: Product `98cd0581`; Harness `fe2839d7`.
- Security: MCP exposed to internal Coolify Docker network, not internet. Avoid assuming an internal bearer key is per-agent authorization.
- Unknown: complete/accurate cross-repo graph; six isolated service nodes and route-only false candidates identified. No validated integration directly through Multica/Hermes sessions.
- Unknown: future GitHub push → automatic private Git fetch → reindex. A one-time indexed SHA is NOT automatic synchronization.
- Privacy: do not embed provider credentials, personal data or full agent transcripts in indexed docs.

**Do not mark overall E2E DONE until the last two unknowns are resolved and evidenced.**
