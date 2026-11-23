# RepoWise MCP — single vendor source, reviewed MCP overlay

The only complete upstream RepoWise 0.60.1 application source lives in `apps/repowise/` (byte-pinned by `scripts/test_repowise_app_source.py`). The MCP-specific HTTP wrapper, pinned Dockerfile, tested `get_answer` override and regression tests live here; **no separate downloaded RepoWise application package or source fork**.

Build from two explicit GitHub-owned contexts at the **same exact commit**:

```sh
docker build --build-context repowise-source=./apps/repowise \
  -f mcp/repowise-mcp/Dockerfile \
  -t repowise-mcp-test mcp/repowise-mcp
```

GitHub PR CI must run that build and its embedded positive/negative branch, stale cache and repo-scoping tests. Trusted-main GHCR Buildah publishing adds the same named context and retains exact SHA/digest attestation. No repo-root Docker context or PyPI wheel.

The production Coolify service `lecwi3emh9hjxir7gphmalie` still runs a local `:HEAD` image. No immutable production digest, same-SHA readback or live authenticated +/- MCP E2E is claimed until CTO review, ZARI-213 HOLD clearance, COO scoped authorization and rollout/rollback. Preserve existing Harness/Product data mounts, credentials, port 7338, and server identities.
