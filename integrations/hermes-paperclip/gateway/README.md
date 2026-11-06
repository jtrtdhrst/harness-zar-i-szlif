# Hermes Gateway build and Paperclip per-run MCP receiver candidate

**Canonical current status, evidence and end-to-end operations:**
[Hermes operations and E2E runbook](../OPERATIONS-STATUS.md).
H01 adapter/security source review was independently approved by CTO on
2026-11-04 for source commit `792598741832c31d91d74c8de9e787639944d13e`.
This is **not** approval for Hermes release or agent migration.


Source of truth: miloszspyrka-code/harness-zar-i-szlif. Base image:
nousresearch/hermes-agent:v0.22.5, upstream source commit
bf0203a794a07aac3ff764972ab9087baa4e4f4e.

Coolify candidate build contract: use the **per-service reviewed promotion policy**
(PR #41 merged), not an assumed globally forced `main` branch. Build context
`/integrations/hermes-paperclip/gateway`, Dockerfile `/Dockerfile`,
watch path `integrations/hermes-paperclip/gateway/**`, health
GET http://127.0.0.1:8642/health. Persistent /opt/data and existing profile keys
remain managed by Coolify. No secrets in the image or Git.

## Runtime patch (source pinned)

install_run_mcp.py checks SHA-256
a9c3b02e51407ca30fc948753149984c0ec75dcc047763cf75a356c1baaba466
for the pinned Hermes gateway/platforms/api_server_runs.py and fails the
build on drift. It then installs a private ephemeral bridge using Hermes'
existing session_local_mcp._borrowed registry; run_mcp.py validates the grant.
The isolated image build and Python compilation passed; runtime rejects
unauthenticated admission with 401 and malformed/empty run grants with 403.
This is not yet proof of a positive Paperclip-issued run.

## Wire contract — adapter and receiver

The Paperclip Hermes adapter POSTs to the named profile's /v1/runs endpoint
using that profile's distinct API_SERVER_KEY. X-Paperclip-Run-Id contains the
canonical Paperclip run UUID. Private JSON field paperclip_run_mcp carries:
version=1, company_id, agent_id, issue_id, run_id, profile,
scopes=["tools:call"], expires_at (ISO UTC) and
servers=[{name, url (HTTPS), token (opaque Paperclip bearer)}].

Security boundary for bearer destinations (verified production issuer contract on 2026-11-06):
- Existing legacy destination remains the **exact** HTTPS URL `https://paperclip-mcp.zariszlif.pl/mcp`, or separately operator-listed exact HTTPS `/mcp` URLs via `HERMES_PAPERCLIP_MCP_URLS`.
- **Actual Paperclip Core native issuer** creates run-bound named gateways under `https://paperclip.kompaszbiorek.pl/mcp/gateways/gw_<32 lowercase hex>`; this strict first-party hostname + path pattern is admitted. The Core's exact `/api/mcp/project-tools` and `/mcp/runtime-tools` may also be admitted; all still require independently validated run-specific bearers.
- There is **no wildcard hostname, path suffix, arbitrary `/mcp` subpath, query/fragment, HTTP, port override, URL credentials, encoded-path escape or cross-origin bearer redirect**. Hermes' MCP client enforces `strict_redirect_headers`; Paperclip Core itself validates scope, run, agent, expiry and revocation on every call.
- An explicit empty `HERMES_PAPERCLIP_MCP_URLS` disables **all** borrowed remote MCP servers (including the first-party Core routes). A request body can never extend the allowed origins. Tests in `tests/test_run_mcp.py` cover valid gateway URLs, SSRF/path negatives and operator disable semantics.

Root cause of the 2026-11-06 first true Designer canary HTTP 403: the former Hermes receiver only allowed `/mcp` on the external MCP host and therefore rejected Paperclip's **real** `/mcp/gateways/gw_<id>` URLs before a tool could run. This patch fixes that versioned wire mismatch without copying a token to logs or changing Paperclip's issuer authority.

The receiver strips paperclip_run_mcp before routing, prompts, session history,
durable run status or Opik. The tool config is registered only while the
synchronous agent turn is running and cleared on exit/error. The caller-provided
run ID and profile cannot on their own confer authorization: the profile
API_SERVER_KEY authenticates the route and the Paperclip MCP gateway verifies
the original short-lived bearer and actual grant on EVERY tool call, including
run/agent identity, access and revocation.

The adapter MUST set sessionKeyStrategy=run and provide an actual UUID. It
derives the profile from the named URL, uses only runtimeMcp.getServers()
(not payloadTemplate), sends its token only in the ephemeral request, and
redacts the bearer in every error/log path. The local expires_at is an
admission bound, not a substitution for the issuer's token expiry.

## Validation and remaining release gates

- Standalone Python grant-validation tests: 4/4 PASS.
- Installer dry-run against exact running pinned source checksum: PASS.
- Isolated Docker build and Python compilation: PASS.
- Local isolated container module import, HTTP health 200: PASS.
- Unauthenticated POST returned 401; authenticated malformed/null grant 403.
- **Historical** adapter Vitest 104/104 and TypeScript PASS in earlier worktree.
- **Current approved H01 source**: Vitest 114/114, adapter TypeScript PASS,
  `git diff --check` PASS; pinned image Vitest 108/108, adapter TypeScript
  PASS; source SHA-256 exact match; 3/3 code-HEAD GitHub CI SUCCESS.
- A real local HTTP 307/308 redirect regression using **synthetic** bearer
  produced zero redirected-target calls and zero detected token disclosures.
  These checks do **not** prove a real Paperclip-issued token path.

BLOCKED for production **despite the completed independent H01 CTO source review**:
real Paperclip-issued token and named profile authentication; native Named MCP
Wiki + Skills read with positive and negative run/agent authorization; Hindsight
selfhost retain, separate session exact recall and cross-bank denial; Opik
thread_id and task_id with the SAME real Paperclip run UUID; reviewed merge,
GitHub-to-Coolify exact SHA/digest, rollback and cohort-by-cohort verification.
No Core edits, Cloud data deletion or mass agent cutover permitted.

## Audited native run-scope positive controls — 2026-11-04

The source-pinned candidate image was rebuilt from current receiver code, not reused from an older image:

- GitHub receiver PR #36 candidate revision `965ad5a77bcea3a9fd837c628fda21c27c0ba915`.
- Docker image (isolated, NOT production): `hermes-gateway-runmcp-candidate:965ad5a`, image ID `sha256:afb7651ccd0a41f82483c1784cee3d6eb79fbbabbcb7e2cf57f0e7ab5ade6e51`.
- Image `/opt/hermes/gateway/run_mcp.py` SHA-256 `b9fcbaed6f1ac385cc5497438514a2aa2b7ce01c1d2cc5457215d3a8aaccf80a` matches the actual GitHub source.
- `python3 -m py_compile` and image import of modified Hermes `_RunLaunch` **PASS**.
- New `tests/test_run_mcp_scope.py` supplies 5 native-registry seam tests: positive scoped registration and cleanup, concurrent role/run isolation, wrong-profile admission denial, missing-discovery rejection, cleanup under agent exception. Combined with 7 grant/auth tests: **12/12 PASS**, repeated using the newly built image in `--network none` with synthetic test credentials.
- **Not real external MCP E2E:** the scope tests mock only the native `_borrowed` registry boundary; no real Paperclip-issued bearer, real Wiki call, or correlated Opik Hermes trace is asserted. No production container or profile was altered.

**Historical note only:** this earlier candidate had a wedged reviewer and
missing H01 approval. That condition was resolved: Paperclip issue
`KOMAA-1564` is `done` with independent first-class CTO approval at
2026-11-04 19:14 UTC. H02/H05, the real issuer-bound Wiki/Skills test,
negative grant lifecycle tests, Hindsight cross-bank checks, same-run Opik,
GitHub/Coolify digest promotion and rollback **remain separate release gates**.
The authoritative, ordered checks and evidence requirements are in the
[operations runbook](../OPERATIONS-STATUS.md).
