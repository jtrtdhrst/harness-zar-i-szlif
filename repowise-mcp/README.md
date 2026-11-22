# RepoWise Harness MCP (Git-owned build)
The live Coolify service `lecwi3emh9hjxir7gphmalie` runs RepoWise **0.60.1** and hosts the Harness/Product MCP indexes. This source builds an equivalent pinned MCP executable; existing live containers/volumes stay unchanged until a separately approved cutover.

## Coolify Git deployment configuration
- Source: private GitHub `jtrtdhrst/harness-zar-i-szlif`, reviewed commit of `main`.
- Build Pack: **Dockerfile**. Base Directory: `/repowise-mcp`; Dockerfile Location: `/Dockerfile`.
- Internal port: `7338`. Disable auto-deploy during the release HOLD.
- Copy existing runtime environment keys through **Coolify secrets**, never into Git; `REPOWISE_API_KEY`, `REPOWISE_DB_URL`, `REPOWISE_EMBEDDER`, `REPOWISE_EMBEDDING_MODEL` may be required by the existing runtime.
- Preserve existing workspace/index volume and Codex-state volume only after a consistent backup and single-writer cutover. Do not mount the current writable index into a concurrently running candidate.
- In staging, provide an independent index volume and check `repowise --version`, MCP handshake, tools/list, authenticated access, unauthorized 401, and exact indexed HEAD.

## Edit the actual MCP Python implementation
The pinned RepoWise 0.60.1 wheel is installed first. The Docker build then copies **only reviewed existing .py modules** from `overrides/<path-under-repowise-package>` into its installed package. The script rejects missing targets, non-Python files, and symlinks. For example, to customize the MCP HTTP router, commit the complete reviewed replacement at `overrides/server/routers/mcp.py` (based on the exact installed 0.60.1 source). For CLI integration code, the package path is `overrides/cli/commands/mcp_cmd.py`. Always compare the original vendor file/diff and run integration tests; an override changes upstream code and must not weaken auth.

This provides source-level edits from the Harness repo **without silently upgrading upstream RepoWise**. Hindsight's repo-owned MCP source is the gateway Caddyfile, not the memory engine. The original upstream repositories are maintained separately.

## Release gate
Feature branch → independent exact-SHA review → CI and isolated Docker smoke → authorized Coolify update → running image digest/endpoint readback and rollback. An enabled MCP assignment is not evidence the agent can execute it.
