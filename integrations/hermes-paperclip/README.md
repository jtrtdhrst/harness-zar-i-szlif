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
python3 integrations/hermes-paperclip/verify_e2e.py --evidence integrations/hermes-paperclip/evidence.example.json
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
