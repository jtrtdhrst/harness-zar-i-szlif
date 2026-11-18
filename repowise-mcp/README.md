# RepoWise Harness MCP (Git-owned build)
The live Coolify service `lecwi3emh9hjxir7gphmalie` runs RepoWise **0.60.1** and hosts the Harness/Product MCP indexes. This source builds an equivalent pinned MCP executable; existing live containers/volumes stay unchanged until a separately approved cutover.

## Coolify Git deployment configuration
- Source: private GitHub `miloszspyrka-code/harness-zar-i-szlif`, reviewed commit of `main`.
- Build Pack: **Dockerfile**. Base Directory: `/repowise-mcp`; Dockerfile Location: `/Dockerfile`.
- Internal port: `7338`. Disable auto-deploy during the release HOLD.
- Copy existing runtime environment keys through **Coolify secrets**, never into Git; `REPOWISE_API_KEY`, `REPOWISE_DB_URL`, `REPOWISE_EMBEDDER`, `REPOWISE_EMBEDDING_MODEL` may be required by the existing runtime.
- Preserve existing workspace/index volume and Codex-state volume only after a consistent backup and single-writer cutover. Do not mount the current writable index into a concurrently running candidate.
- In staging, provide an independent index volume and check `repowise --version`, MCP handshake, tools/list, authenticated access, unauthorized 401, and exact indexed HEAD.

## Source extension
This Dockerfile is the owned build/packaging entry point. To edit RepoWise's **upstream implementation**, use an explicitly version-pinned upstream patch or vendored source and a reviewed build test; do not imply that altering this Dockerfile edits Python tools from the installed wheel. RepoWise code upstream: https://github.com/repowise-dev/repowise (the version here matches the live runtime).

## Release gate
Feature branch → independent exact-SHA review → CI and isolated Docker smoke → authorized Coolify update → running image digest/endpoint readback and rollback. An enabled MCP assignment is not evidence the agent can execute it.
