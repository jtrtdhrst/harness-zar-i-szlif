# Production recovery ledger

**As of:** 2026-11-03 22:30 UTC  
**State:** mission is not complete. This is an evidence ledger, not a green-status summary.

Use only these states: **PASS** means verified in production; **FAIL** means a current defect was observed; **BLOCKED** means an explicit prerequisite prevents safe progress; **NOT TESTED** means evidence is insufficient. Historical results are labeled as historical and do not satisfy live acceptance.

## Current workstreams

| Workstream | State | Evidence | Next action |
|---|---|---|---|
| Product production release, PR #148 | PASS | Independent CTO decision approved exact head 908b8544d30e01e0f282e67c01070f0e450e9b41. Merged to main as 06d6a10eb5a5d13c47aa9d958b4874954bb8e5da. Coolify deployment xsv4eyouqa7wuruclbxzse36 finished on that SHA; running image digest sha256:131af468c13642a850a84fabb6545c734fe992134cf780cf373cbe244ca95f57 was healthy. Public /healthz returned 200 text/plain with exact body ok\n; / and existing redirects were checked. | No follow-up deployment required. |
| Paperclip MCP live endpoint | PASS | Native live verification returned authenticated initialize/tools/list/call 200 and anonymous 401; 200 tools. Running image, service and recorded source commit matched 1b4c803816e82b0265c8422e1a804327a7ed8c54. | Keep this as the MCP transport baseline; agent-to-Hermes integration remains separate. |
| Cloudflare Workers preservation | PASS | Inventory returned the existing three scripts: stronaglowna, zariszlif-prawne, paperclip-mcp. No worker was changed or added in this execution. | Preserve these exact workers during remaining work. |
| Paperclip agents → Hermes | FAIL | Current inventory still shows 14 active agents on opencode_local / legacy; migration remains 0/14. A real CHO run previously failed Hermes authentication with HTTP 401, and the required current Paperclip → Hermes run has not passed. | Repair the authenticated adapter path, then canary a single agent and migrate cohorts only after all acceptance checks pass. |
| Run-scoped MCP receiver / Hermes adapter | BLOCKED | Open PR #18 is a fail-closed candidate, not a working bridge. KOMAA-1564 worktree HEAD 4d90f3bc8a6f7f20dad8b86b9f7b797e69168f73 changes only adapter execute code/tests to reject unsupported grants. Inspection of Hermes v0.22.5 source found no runtimeMcp or mcp_servers field in POST /v1/runs; the source has session-local editor_mcp/session.mutate machinery, but no HTTP run-scoped receiver in this contract. | The board must approve a version-pinned receiver contract through parent KOMAA-1512 before adapter transport work proceeds. Never put the token in prompts, persistent profile config, logs or traces. |
| Hermes Gateway runtime container | PASS | Read-only host readback via SSH on 2026-11-03: Docker container 2sganhxhhnioiqh4an9g2f4k-20261103T191132 is running and healthy, image digest sha256:813992ff23d9b82936ad5f35ed9f1d74908584d44888197b492c4615680cd65a. Local GET 127.0.0.1:9119/api/status returned HTTP 200, version 0.22.5, gateway_running=true and gateway_state=running. This is runtime health only; it does not prove a Paperclip agent run or GitOps deployment. | Keep the current serving container while repairing the source-controlled release path; verify actual agent execution separately. |\n| Hermes Coolify GitOps | FAIL | The Coolify application remains degraded:unhealthy, source_type is null, git_repository is coollabsio/coolify, and the app Dockerfile is inline. Latest deployment zptpaiej83xnw9gpohjv1yzm failed after the health probe invoked missing wget. Host readback shows the prior container still serving from image digest sha256:813992ff23d9b82936ad5f35ed9f1d74908584d44888197b492c4615680cd65a; this is an old live artifact, not the candidate release. PR #31 is open and unreviewed; exact head f3544ca78b85a44514ddab8a918db1919c2e9e2c has successful GitHub Actions runs 41717392897 (Hermes Gateway Coolify Image CI) and 41717392895 (Paperclip MCP CI), but is undeployed. | Obtain independent review, merge through the approved path, bind the existing app to the existing GitHub App/repository, then verify deployed SHA, digest, health and a functional MCP call. |
| Hindsight / VAI | NOT TESTED | Live VAI enumeration returned exactly 14 hermes-<role> banks, including hermes-ui-qa with zero facts. Historical audit reported 182/182 denied cross-bank attempts, but current bank inventory does not prove run-bound memory mapping or isolation; no Paperclip → Hermes → Hindsight retain/recall cycle was performed in this execution. KOMAA-1553 is in_progress; KOMAA-1549 is blocked. | Run each authorized agent against its own bank, including independent-session recall and cross-bank denials, after the real Hermes bridge works. |
| Opik E2E correlation | FAIL | A live query of the hermes project found 92 traces matching “paperclip.” The latest records carry local-<session> thread/task IDs; the only paperclip:run-shaped record is the synthetic probe paperclip:run:00000000-0000-4000-8000-000000000001, not a real Paperclip run UUID. No correlated production run containing model, MCP and Hindsight spans was proven. | Add stable task/run correlation and verify the trace through the Opik API on a real agent run. |
| Plasmic WAB / MCP | BLOCKED | Plasmic MCP health is 200, but WAB rejects project listing with HTTP 403 “Must be a normal user”; readiness is 503. PLASMIC_EMAIL and PLASMIC_PASSWORD are empty. Pending Paperclip interaction 692fb599-a805-4ef0-83af-7e3545b6841e asks whether the owner will provision a supported identity through approved secret management and restore the scoped tool grant. No credentials or project writes were attempted. | Owner must approve or decline the pending identity/tool-grant interaction. Do not send credentials in chat, comments or logs. |
| ComfyUI agent / mascot | BLOCKED | Public endpoint https://mcp-comfy.kompaszbiorek.pl/mcp returned initialize/tools/list 200 with 44 tools; required upload_chatgpt_image, get_output_image_ref and stage_output_image_reference are listed. Repository contract intentionally allows anonymous access; no auth policy was changed. Mascot Designer’s OPENCODE_CONFIG_CONTENT has no ComfyUI server entry; fresh effective-tool checks return zero tools matching get_system_stats and hindsight. KOMAA-1528 has no work product. A native send-back attempt returned 409 because Paperclip no longer classified it as a stalled review; no mutation occurred. | Restore the authorized MCP tool projection through the existing approved agent path, then verify with Mascot Designer before any image generation. |
| Native review / Harness PR #33 | BLOCKED | PR #33 head a34e093adb1e8319a5004c471e677e1e37a20d69 is open, hosted validate-paperclip-mcp and 75/75 Vitest were reported green. CHO first-class changes_requested and later requested a fresh review of the same exact SHA. Current KOMAA-1559 state is blocked with zero dependency edges but executionState still has a pending review stage (known status-projection defect KOMAA-849); no reviewer run is live. Read-only repair returned no actions; no forced status or review decision was made. | CHO must make the genuine pending decision through a supported native review run. Do not use a GitHub self-review or force an issue status. |
| Other Hermes PRs | BLOCKED | PR #28’s validator documents unresolved real-runtime blockers; PR #18 remains fail-closed. PR #31 CI passed but no independent review or production deployment exists. | Keep open until each exact head has its required real review and production evidence. |
| Cleanup / full E2E matrix | NOT TESTED | Temporary-resource candidates were inspected as candidates only. No services, volumes, databases, Workers or repositories were deleted. E2E 1/2 schedules and all rollback/retry/idempotence paths were not re-run. | Confirm dependency references and recovery path before any deletion; execute the remaining production test matrix after prerequisites clear. |

## Active control-plane records

| Issue | Current state | Evidence / owner |
|---|---|---|
| KOMAA-1512 | BLOCKED | Waiting on KOMAA-1564 and the receiver contract. |
| KOMAA-1513 | BLOCKED | Approved board request exists, but Paperclip MCP/agent runtime GitHub App credentials are not yet provisioned in approved secret management. |
| KOMAA-1549 | BLOCKED | Parent Hindsight / 14-bank Hermes E2E gate. |
| KOMAA-1553 | in_progress | Harness-owned isolated-bank migration and E2E. |
| KOMAA-1556 | in_progress | Product lane is accepted; Harness lane PR #33 remains unresolved. |
| KOMAA-1559 | BLOCKED | PR #33 pending a genuine CHO review; status projection is inconsistent. |
| KOMAA-1535 | in_review | CHO review is idle while the WAB identity interaction is pending. |
| KOMAA-1528 | in_review | No assigned agent, reviewer stage or work product; Mascot runtime tool registration is missing. |

## Live PASS evidence

- Product PR #148: https://github.com/miloszspyrka-code/zar-i-szlif/pull/148
- Harness PR #33: https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/33
- Hermes healthcheck candidate PR #31: https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/31
- Existing Hermes v0.22.5 source used to inspect the run/session boundary: [api_server_runs.py](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/gateway/platforms/api_server_runs.py) and [session_local_mcp.py](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/gateway/session_local_mcp.py).

## Next safe sequence

1. Approve the pinned Hermes Gateway receiver contract through KOMAA-1512; then implement and review the bridge without changing Paperclip Core/shared code or exposing credentials.
2. Complete independent review and exact-SHA GitOps binding/deployment for the existing Hermes app.
3. Resolve the pending CHO review on PR #33 through the native review stage; correct the review-status projection only through an authorized Paperclip control-plane fix.
4. Obtain the owner’s decision on Plasmic WAB identity/tool grant; then perform read-only positive/negative access tests.
5. Restore the Mascot Designer’s authorized original runtime MCP connection and verify it through that principal before any image generation.
6. Run real agent Hindsight, Opik and role/MCP isolation tests; migrate agents in tested cohorts.
7. Reconcile the actual backlog, E2E schedules and infrastructure cleanup only after production dependencies are read back.

No secrets, tokens or credential values are stored in this ledger.