# Multica MCP authenticated E2E canary (operator-run)

This is a **manual, mutating** canary, separate from the read-only CI unit test.
Never run it against the Żar i Szlif production workspace or with a global/admin token.

## Preconditions

- An explicitly approved **disposable TEST workspace**, with no customer data, active agents or real workflows.
- A short-lived, revocable `MULTICA_TOKEN` whose scope is limited to that workspace and allows only the fixture operations needed below (project/issue create, read and cleanup).
- The operator has verified the exact live MCP endpoint and native Multica API endpoint.
- Use a controlled local shell, not an untrusted PR runner. Do not store or print the token in issues, Git, logs or shell traces.

## Execute

From this repository root in the operator's trusted environment:

```sh
export TEST_WORKSPACE_ID='<approved-disposable-test-workspace-uuid>'
export MULTICA_TOKEN='<scoped-test-token>'
export MCP_URL='https://mcp-multifca.zariszlif.pl/mcp'
export MULTICA_API_URL='https://multica.zariszlif.pl'
npm --prefix multica-mcp run e2e
```

The script authenticates `initialize` / `tools/list`, creates a disposable project and issue, checks issue readback and the `structuredContent.items` envelope for list tools, then attempts cleanup. Expected success output is JSON with `status: "PASS"`, `writeReadback: true` and `disposableProjectCleaned: true`.

## Failure and post-run checks

Treat nonzero exit, API 401/403/5xx, malformed `structuredContent`, or failed cleanup as **FAIL**. The script has a `finally` cleanup, but cleanup can itself fail. Confirm the newly created issue and project are absent; if either remains, remove **only those test-owned fixtures** by their recorded IDs with the scoped authorization. Never delete pre-existing projects/issues. Record endpoint, test workspace ID, source SHA, a redacted run log, result JSON and fixture-cleanup readback. Revoke the test token after the run.

## Boundaries

The CI workflow `.github/workflows/multica-mcp-ci.yml` runs `npm test` on a PR touching `multica-mcp/**`. It intentionally does **not** invoke this mutating canary. CI check enforcement, branch rules and actual GitHub-hosted job execution require separate administrative verification. An unstarted job (for example due to billing) is **NOT_RUN**, never PASS.
