# Paperclip Core Hermes adapter-only release image

**Not a fork of Paperclip Core.** This overlay changes only `packages/adapters/hermes/src/gateway/server/execute.ts` on the exact deployed `ghcr.io/paperclipai/paperclip:2026.1023.0` base. The patch was computed from the verified original runtime file (SHA-256 `e3593d03d40b37b215d68342c8d615d26014bf5892eef79151b6153737764701`) and the reviewed, isolated `KOMAA-1564` adapter source (commit `3fc315ed4b70e76c350c168f43b2dc4176786bdc`, SHA-256 `ad69e65cf4827dcc46d33110d80511ce7e09d07030e1e19a2a8a7e3e0c44b249`).

The Dockerfile fails closed on source or output SHA mismatch. The built image passes the adapter TypeScript typecheck. This patch is separate from the Hermes Gateway receiver in [PR #36](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/36); both must be reviewed and deployed for a real issue-run MCP test.

## Delivery

A PR can validate the image but cannot publish it. Only a merged and checked `main` push publishes an immutable GHCR tag `ghcr.io/miloszspyrka-code/paperclip-hermes-adapter:<main-sha>`. The package is **not** automatically deployed to the production Paperclip Core service. CHO must first confirm independent CTO security review, production named-profile secret bindings, negative access control, exact Opik trace and Hindsight isolation evidence. The existing Paperclip Core image/volume must remain available for rollback.

Do not start a second Paperclip Core against the production database or mount; do not edit running containers in place or disable the native review gate.
