# Paperclip Hermes Gateway — bounded adapter candidate (2026-11-03)

**Status: TESTED CANDIDATE; NOT PRODUCTION DEPLOYED.** This is an adapter-only patch, not a modification to Paperclip Core. Do not apply it directly to a running production container or merge it without the CHO-controlled release gate.

## Source pin and verification
Target image: `ghcr.io/paperclipai/paperclip:2026.1023.0`.
Source paths:
- `packages/adapters/hermes/src/gateway/server/execute.ts` preimage SHA-256 `e3593d03d40b37b215d68342c8d615d26014bf5892eef79151b6153737764701`
- `packages/adapters/hermes/src/gateway/server/test.ts` preimage SHA-256 `279504640a2464150ed92210002f400cfbe3d6d3855a6583484e4a120178b7c4`
- `packages/adapters/hermes/src/gateway/server/execute.test.ts` preimage SHA-256 `5cd8988db80e10961a8d80f915513c90001e24a599988b6b9e1f7e5fbf4b4984`
Patch SHA-256 `1ebeb7ef70bc3c55aa4f70c4dd6f82e8a34fa44bf4666f6a2d71984b725125df`.

On an isolated source checkout, run:
```sh
git apply --check integrations/hermes-paperclip/adapter-patches/hermes-gateway-20261103.patch
git apply integrations/hermes-paperclip/adapter-patches/hermes-gateway-20261103.patch
cd packages/adapters/hermes
pnpm exec vitest run --config vitest.config.ts src/gateway/server/execute.test.ts
pnpm exec tsc --project tsconfig.json --noEmit
```
If the patch lives outside the Paperclip source tree, pass its absolute path to git apply.

## What this changes
1. **Real credential preflight:** a green public `GET /health` no longer proves authentication. `POST /v1/runs` with intentionally malformed JSON must return HTTP 400 for the configured credential and 401/403 for an intentionally invalid credential. A valid run cannot be started by the malformed probe, so it consumes no model tokens. Wrong-profile secret 401 returns FAIL.
2. **Role instructions:** the authoritative `instructionsFilePath` under the supplied `instructionsRootPath` is checked with realpath containment, regular-file status and 150 KB bound, then passed as an *ephemeral system instruction* for this Hermes run, not as user text or a persistent shared profile field. Missing/unsafe configured bundles fail closed.
3. **No silent MCP grant drop:** when `ctx.runtimeMcp` or `ctx.runtimeTools` carries ephemeral per-run grants, the adapter returns `hermes_gateway_run_scoped_mcp_bridge_required` before dispatch, rather than launching a Hermes turn with missing permissions. No bearer token is logged, placed into a prompt, or written to a persistent profile.
4. Regression tests explicitly exercise wrong-route credentials, invalid-key negative controls, role injection/exclusion from user prompt, path escape denial and fail-closed handling of scoped credentials.

## Bounded test evidence
On the VPS, this patch passed `106/106` focused Vitest tests and the adapter TypeScript check in a disposable, **network-disabled, read-only container** using the current Paperclip production image. `git apply --check` passed against the same image. No running Paperclip, Core source, Hermes credential or production agent adapter was modified.

## Still blocked: actual run-scoped MCP bridge
Paperclip already generates run-scoped MCP grants in `server/src/services/heartbeat/run-preparation.ts` and passes them via `AdapterExecutionContext.runtimeMcp`. The existing Hermes Gateway adapter does not implement transport and Hermes Gateway `/v1/runs` has no verified private, ephemeral MCP override contract. Until a reviewed integration exists that binds each grant to **the exact agentId + runId + session, expires/revokes it, rejects cross-agent/cross-run access, and never logs or persists the secret**, this patch must intentionally fail closed. `wiki_fs` readonly smoke checks are not substitutes for the assigned Paperclip MCP tools.

The generic Paperclip adapter key also failed a real CHO run with `hermes_gateway_auth_failed` (KOMAA-1546), and the connection/security layer refused an automated transfer of private CHO profile credentials. Enroll the dedicated key through the approved Paperclip encrypted-secret workflow. Do not bypass this boundary using SSH/DB/alternate encodings.

**No bulk migration or deployment success until** an authenticated native Paperclip → Hermes CHO run succeeds with its correct model and authorized named MCP tool call, native Hindsight retained/independent recall, same-run Opik correlation, independent CHO acceptance, verified production image digest, and rollback test. The 14 agents remain on `opencode_local` until those gates are green.
