# Hermes Gateway build and Paperclip per-run MCP receiver candidate

Source of truth: miloszspyrka-code/harness-zar-i-szlif. Base image:
nousresearch/hermes-agent:v0.22.5, upstream source commit
bf0203a794a07aac3ff764972ab9087baa4e4f4e.

Coolify production contract (after review): branch main, build context
/integrations/hermes-paperclip/gateway, Dockerfile /Dockerfile,
watch path integrations/hermes-paperclip/gateway/**, health
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
- Adapter Vitest 104/104 and TypeScript PASS in independent Paperclip worktree.

BLOCKED for production until: independent CTO/CHO source review; real
Paperclip-issued token and named profile authentication; native Named MCP
Wiki + Skills read with positive and negative run/agent authorization; Hindsight
selfhost retain, separate session exact recall and cross-bank denial; Opik
thread_id and task_id with the SAME real Paperclip run UUID; reviewed merge,
GitHub-to-Coolify exact SHA/digest, rollback and cohort-by-cohort verification.
No Core edits, Cloud data deletion or mass agent cutover permitted.
