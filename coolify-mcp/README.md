# coolify-mcp

Coolify MCP source and deployment project. Complete upstream-derived application
source (MIT, pinned v3.10.1) and owned release tools live directly in this folder.
Build context: `coolify-mcp/`; Dockerfile: `coolify-mcp/Dockerfile`.
Runtime data volumes remain outside Git; only `volumes/` markers are committed.

- Project metadata: `project.yml`
- Runtime source/image: see `docs/COOLIFY-PROJECTS.md`
- No secrets or runtime data in Git.

See `UPSTREAM.md` for exact provenance, opt-in release evidence tools, and test/deploy policy.
