# Hindsight MCP bank-isolated gateway (Git-owned source)
The live Coolify MCP gateway is service `aglen8ervlo2lpi30oz8iii9` and the existing Hindsight core is `hjda7ckq5z4luhd1vpdepi0r`. This source controls the MCP gateway **only**; Hindsight's upstream core uses `ghcr.io/vectorize-io/hindsight:latest-slim` at observed revision `34a138684a899b6ec34175f7a2b633860466d289`. The current core PostgreSQL and OAuth volumes must not be recreated.

## Coolify Git deployment configuration
- Source: private GitHub `miloszspyrka-code/harness-zar-i-szlif`, reviewed `main` commit.
- Build Pack: Dockerfile; Base Directory: `/hindsight-mcp`; Dockerfile Location: `/Dockerfile`.
- Internal port: `8080`. Use network connectivity to the **existing** `hindsight:8888` and `hindsight-admin:8888` upstreams (currently the Coolify Docker network). Do not expose direct Hindsight upstream to the internet.
- Inject role-specific `HINDSIGHT_BANK_TOKEN_<ROLE>` (14 entries), `HINDSIGHT_UPSTREAM_MCP_TOKEN` and `VECTORIZE_ADMIN_MCP_TOKEN` through Coolify secrets. Never copy their values to Git or container logs.
- Preserve `/mcp/hermes-<role>/*` and 3 allowed POST API paths per bank; wrong-role tokens and other paths must fail closed.
- Stage with dummy credentials and a fake upstream first. Deploy only after isolated auth positive/negative cases, test exact running image digest, and verify every role's existing MCP binding.

## Ownership boundary
Harness Engineer can edit Caddy routes, auth policy, and Dockerfile on a scoped branch. This does **not** vendor or authorize editing the upstream Hindsight Python memory core. Core changes require a separately reviewed fork/source build and database compatibility tests.

## Release
Respect active `ZARI-213` isolation HOLD. No agent should receive unrestricted cross-repo writes, secrets or deployment rights until server-side ACL/isolation is independently proven. Coolify promotion is operator-only with a verified rollback.
