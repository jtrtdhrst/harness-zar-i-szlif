# RepoWise MCP — canonical GitHub source and HTTP deployment

The **only** application and MCP implementation source is the complete RepoWise 0.60.1 tree in `apps/repowise/`. This folder retains the migration contract and historical PR #196 provenance, not an independent code fork or downloaded package.

- Source: `apps/repowise/packages/server/src/repowise/server/mcp_server/tool_answer/answer.py`
- Source build: `apps/repowise/docker/Dockerfile.mcp`; build context `apps/repowise/`
- Real behavioral regression: `apps/repowise/tests/unit/server/test_answer_branch_routing_owned.py`
- CI: `.github/workflows/repowise-mcp-ci.yml` (PR gates) + `.github/workflows/mcp-images-ghcr.yml` (trusted main SHA-bound GHCR publisher)
- Coolify existing service UUID: `lecwi3emh9hjxir7gphmalie`, **still running local `:HEAD` until authorized release**
- Preserve existing Harness/Product repo volumes, private environment configuration, internal port 7338, and rollback. Do not include runtime data, tokens, or private config in Git.

The MCP build installs its package from `apps/repowise` using `pip install .`. No PyPI RepoWise application wheel, alternative local image source, or repo-root Docker build context is permitted.

**Release:** exact reviewed main SHA → tested GHCR immutable digest → independent security isolation clearance (ZARI-213) and COO per-UUID authorization → Coolify image parity → authenticated positive and negative HTTP MCP tests → rollback proof. A green image build is not deployment approval.
