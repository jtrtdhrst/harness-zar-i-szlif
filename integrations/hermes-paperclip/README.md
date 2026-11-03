# Hermes ↔ Paperclip — infrastructure E2E harness

**Repository:** `harness-zar-i-szlif`  
**Owner:** Paperclip project `04 · Operations / Hermes-Paperclip E2E`  
**Coolify:** `Hermes - Paperclip Sync` (standalone read-only check service)  
**Runtime documentation:** `/opt/hermes-paperclip-sync/` on the VPS.

## Execution contract

Paperclip is the **control plane** (tasks, approvals, published Wiki and skills); Hermes Gateway is the **runtime**, one named Hermes profile per Paperclip agent; Hindsight (Vectorize.ai) is profile-isolated memory; Opik is tracing. Wiki is canonical Markdown in Paperclip, read *live* through its Named MCP Gateway; do not copy unreviewed content into the approved Wiki. Skill changes must be reviewed and versioned. **No Paperclip Core modifications.**

## Safety boundaries

- Do not disable authentication, forward vault secrets into logs, share keys across profiles, copy files from other agents, expose private admin routes or publish diagnostics publicly.
- Do not re-enable company-wide watchdogs, cron, routines, heartbeats, or GitHub Actions.
- Each task runs on an isolated git worktree derived from `main`, with branch identity traceable to its Paperclip issue; one writer per branch.
- Only the `Hermes Test` agent and the bounded integration scope may be mutated during the initial acceptance. No prod cutover until independent review.
- Watchdog is native and attached **only** to the test epic. It monitors stopped subtree work, not a polling replacement; can escalate but never self-approve or automatically merge.
- Preserve Coolify's existing Gateway and sync-project deployments until rollback/readback acceptance.

## Definition of Done (all required, none implied by a green healthcheck)

1. A **dedicated** Hermes `hermes-test` API key exists and is stored as an encrypted Paperclip `secret_ref`. The Paperclip adapter points to `/p/hermes-test`. A real authenticated profile request succeeds; default/wrong key is rejected. No value is printed in evidence.
2. Paperclip Tool Connection's Bearer is valid for its configured MCP host; **actual `tools/call`** for a page in `wiki/agents/ceo/AGENTS.md` succeeds in a Paperclip-issued Hermes Test run. `initialize` and `tools/list` do not count as E2E.
3. The same run reads a published skill version and records its ID/version marker. No unauthorized writes.
4. The Hermes `hindsight` provider retains and later recalls a synthetic marker in the `hermes-hermes-test` bank. Control bank `hermes-ceo` must not return it.
5. Opik records a **correlated** trace for that same Paperclip run, with model, tool spans and token usage. Synthetic unrelated traces do not count.
6. Paperclip run ID, Tool Gateway invocation ID, Opik trace ID, named profile ID, published skill version, deployed digest/SHA, smoke status and rollback check are captured in one evidence JSON.
7. Independent CTO review of scope/security + independent Delivery & Release Manager acceptance of reproducible deployment; no self-review. All dependencies resolved, no live run or untracked changes, then issue closure.
8. Documentation, scripts and tests are committed to a feature branch and PR; `main` changes only after review and explicit production approval.

## How to run tests

```bash
python3 integrations/hermes-paperclip/verify_e2e.py --evidence integrations/hermes-paperclip/evidence.example.json --expected-profile hermes-test
python3 -m unittest discover -s integrations/hermes-paperclip/tests -v
```

The example evidence is intentionally **not passing**. The validator returns nonzero until all real artifacts have been collected. Do not create fabricated success receipts.

For local origin-only checks: `sudo /opt/hermes-paperclip-sync/check.sh`. Its green state validates mounts and HTTP auth **only**.

## Known starting faults, 2026-11-01

- Named profile `hermes-test` has no dedicated `API_SERVER_KEY`; existing agent adapter calls unprefixed root Gateway URL.
- Paperclip Tool Connection `7551d8ac-ce4b-4af9-a2af-eefe3cfd63c5` allowed `paperclipWikiGetPage`, but the upstream returned HTTP **401** (surface error 502 `mcp_remote_status`). Health/catalog are not sufficient.
- The plugin Wiki variant fails from standalone CLI without a Paperclip agent-run context.
- Hindsight retain→recall and test-vs-CEO bank isolation were verified on their own; Opik is not yet correlated in the same run.
- Credential modification was rejected by the tool's security gate. Use an authorized secret-management action; **do not bypass** via shell, alternate encoding, database direct writes or shared token reuse.

## Files

- `verify_e2e.py`: strict evidence gate, standard Python only.
- `evidence.example.json`: deliberately failing, redacted example.
- `tests/`: unit tests for the verification gate.

## Pilot E2E results — 2026-11-02 (actual connected services)

**Scope:** Hermes Test is the only agent currently using `hermes_gateway`. This is a **temporary test configuration**, **not** a hard-coded platform policy or limit on future adoption. The accidental adapter-count guard was removed from this PR. Production migration of additional agents is a separate decision after pilot acceptance.

The real Paperclip issue-scoped run is `aca4eae6-8426-4ea9-952c-98498bcb9681` on `KOMAA-1507`. The encrypted Hermes Test API key was re-enrolled through native Paperclip Vault rotation (existing secret, version 2); the prior 401 was eliminated without disabling authentication or touching Paperclip Core.

In that real run: `gpt-6-luna` invoked the actual Paperclip Named MCP `papercliplistskills` and `paperclipgetskillfile`, confirmed published skill marker `KNOWLEDGE_SYNC_V2_20261031`, and called native `hindsight_recall` successfully. Opik trace `01a19c69-cbb1-7106-9088-1f56407e3ce0` has tool spans and references the exact Paperclip issue in `metadata.task_id`. A distinct read-only cross-bank test confirmed no results for the synthetic Hermes Test memory in the CEO bank.

**Blocking failure:** `paperclipai.plugin-llm-wiki:wiki_list_pages` returns `Plugin tools require an agent run context` when invoked from the real Hermes Gateway session, despite an issue-bound Paperclip invocation. The Paperclip Named MCP transport currently lacks the trusted execution context that the native plugin requires. This is **not** fixed by model changes, MCP catalog discovery, or retrying prompts. The Opik trace metadata also contains the issue ID, not the exact Paperclip run ID; stronger structured correlation is still required for strict release evidence. The issue is blocked without automatic retries until runtime context is fixed.

**Acceptance receipt:** `evidence/2026-11-02-canary-v2.json` contains factual partial passes and explicitly failing flags for Wiki, structured Opik run correlation, release, and independent CTO review. Run `verify_e2e.py --expected-profile hermes-test` against this file; **BLOCKED is the expected honest result**, not a test-suite defect. Do not merge or perform production cutover on partial proof.

## Native per-run MCP contract — confirmed gap (2026-11-02)

Paperclip already prepares short-lived `heartbeat_run` tokens for **local adapter** MCP assignments in `server/src/services/heartbeat/run-preparation.ts`. Its Tool Gateway rejects native plugin calls from a reusable `gateway_client` bearer without `session.runId` (guard in `server/src/services/tool-gateway.ts`, `Plugin tools require an agent run context`). Hermes Gateway currently uses a static Named MCP `gateway_client` token from the profile configuration. Thus a live issue-bound Paperclip run **does not automatically make** Hermes's downstream MCP session run-bound.

This must not be “fixed” by trusting an unsigned run header or adding the shared COO principal to a Board Wiki allowlist. The correct adapter-level design is to deliver a *fresh Paperclip-issued, run-bound MCP token* to the Hermes Gateway runtime during `POST /v1/runs` as a server-side secret, register it only within that run's MCP tool scope, revoke/expire on completion, then verify that the native Wiki plugin receives the **same authenticated** `agentId` and `runId`. The current Hermes `/v1/runs` request does **not** expose a verified runtime MCP override; do not pretend `payloadTemplate` or a prompt embeds trusted credentials.

### Run-scoped bridge feasibility — updated 2026-11-03

Hermes v0.22.5 does have private ephemeral MCP machinery in `gateway/session_local_mcp.py`: `_borrowed()` enters `tools.registry.session_tool_scope`, registers servers with per-scope names, keeps the server specs in owner memory, and tears connections down when the last borrower exits. Durable session policy stores only a fingerprint and frozen schemas, not credentials. `editor_mcp_scope()` connects that facility to the canonical session execution policy. This corrects the earlier assumption that Hermes has no private scoped MCP runtime support.

The capability is not yet a `/v1/runs` bridge. `api_server_runs._handle_runs()` maps a fixed `_RunLaunch.agent_kwargs` allowlist and does not read `runtimeMcp` or pass an editor MCP policy into the execution scope. The general `editor` launch field is validated as ACP-only by `gateway/session_local_editor.py`; it cannot simply be added to ordinary API-run JSON. Paperclip's `runtimeMcp` is available only inside its authenticated adapter execution context, not to a sidecar. Thus an external proxy or an unsigned run header still cannot establish trusted run identity.

The feasible path is a reviewed in-process runtime extension: Paperclip's Hermes adapter must deliver its native grant and structured run/issue/agent identity over a private authenticated channel; Hermes must validate the channel and grant, bind the MCP server inside the matching API run's private scope (reusing the existing owner-memory/connection-lifecycle machinery), and tear it down on every terminal/error/cancel path. The run binding must be derived from authenticated grant claims, reject replay/wrong-run/wrong-agent/profile, and never trust caller-supplied IDs alone. The specific `_borrowed()` API is private implementation, not a supported external RPC; no documented owner RPC or approved Hermes source workspace is available in this issue workspace. Keep the adapter fail-closed until the runtime extension is implemented and tested in staging with concurrency, replay, expiry, teardown, restart, and credential-redaction checks.

The present workspace contains the harness/readiness gate but not the Paperclip Hermes adapter or Hermes Gateway runtime source, and this run has no Hermes staging/runtime connector. It therefore cannot make or verify the in-process runtime extension here. No Paperclip Core changes, static profile config edits, or sidecar identity shims are acceptable substitutes.

`verify_e2e.py` requires an explicit `--expected-profile` and evidence for run/issue/agent/Hermes IDs, per-run credential revocation, and wrong-run/wrong-agent/missing-credential rejection. Profile credential readiness requires an authenticated malformed `POST /v1/runs` probe (HTTP 400/422 after authentication), a separate invalid-key rejection (HTTP 401/403), and an explicit statement that `/health` alone is insufficient. Early-auth rejection is a separate acceptance-suite attempt: require its own attempt ID, HTTP 401/403, adapter-edge Opik trace, and no Hermes run ID (the request was rejected before admission); never equate it to the successful Hermes run. This offline verifier cannot authenticate user-authored JSON or fetch Paperclip/Opik records. It therefore reports structural results only and exits `UNVERIFIED` until authoritative readbacks are retrieved; a JSON `passed: true` is not acceptance evidence.

### Subsequent on-server regression

Hermes Test adapter `sessionKeyStrategy=run` is deployed in native Paperclip config. In real issue-bound run `108d5a0b-8642-44d5-8e11-77fc4f9ebd20` (issue `KOMAA-1511`), Opik trace `01a19c80-937a-74de-b56a-b6a3755df5c4` has **exact** `metadata.task_id=paperclip:run:108d5a0b-8642-44d5-8e11-77fc4f9ebd20`. This resolves run-ID correlation without custom code.

The same run's Named MCP skills tool failed `Tool not found` while the remote connection had transient health `HTTP 403`; native health-check restored the connection and three separate governed filtered skill-list tools/call succeeded (`b920ef6e...`, `a8aad5fa...`, `7c2546b8...`). This demonstrates a *separate* connection-health/catalog race requiring bounded healthy discovery before inference, not evidence that Wiki has been fixed.

Acceptance remains **NO-GO** until (a) run-scoped Wiki call succeeds from Hermes's own execution, (b) retries on a blocked issue stop, (c) Hindsight retain + later recall and isolation are proven for that deployment, (d) Opik correlates the same run, and (e) independent review approves the actual artifact. Existing Paperclip Core and all other agent adapter assignments remain unchanged.
