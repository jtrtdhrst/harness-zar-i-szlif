# Paperclip nonterminal triage ledger — 2026-11-11 (ZARI-138)

Scope: the 29 nonterminal Paperclip issues recorded in the 2026-11-11 live verification
(1387 total: 879 done, 479 cancelled, 10 blocked, 2 in_progress, 16 in_review, 1 todo).
Paperclip is read-only: this ledger performed **no Paperclip write, rerun or deletion**.

## Evidence base and its limits

| Source | What it proves | Limit |
| --- | --- | --- |
| Live Paperclip count/status list in ZARI-138 (creator verification, 2026-11-11) | 29 nonterminal keys and their current status | Not re-read by this run (no Paperclip DB/docker/API credential in this runtime) |
| `docs/migration/paperclip/2026-11-11/` archive (`9a1e2bb`, 1260 records) | title, status-at-extraction, project, parent and first-class blockers for 15 of 29 keys | 14/29 keys absent (10 chat records + KOMAA-252/797/1464/1518); statuses frozen at the 2026-11-06 extraction |
| Harness `main` git history | `5d9c29d` PR #98 (per-agent run-scoped MCP projection lock), `ad0cf80` PR #99 (multica-mcp `items` envelope) | — |
| `multica-mcp/` source + tests + catalog | 184 tools discovered from the pinned Multica v0.8.1 CLI; `docs/paperclip-parity-matrix.json` labels all 200 observed Paperclip operations `ARCHITECTURALLY_INCOMPATIBLE`; OAuth explicitly not implemented; `tests/server.test.mjs:39` asserts `401` on unauthenticated calls | Adapter surface, not Multica product behavior |
| Multica issue record ZARI-1..137 | 14/14 named Hermes role canaries (ZARI-60/76), own-bank Hindsight + RepoWise + Opik traces (ZARI-80..93), post-deploy canary after host sync to `5d9c29d` (ZARI-131), multica-mcp fix live (ZARI-132, ZARI-134) | Canary evidence is per-role, not per-capability certification |
| ZARI-137 (blocked) | the authoritative list of remaining owner/credential blockers | owner action, not agent work |

Disposition vocabulary: `TRANSIENT` (chat/transient, archive only), `SUPERSEDED` (its subject was
replaced or retired and the outcome is delivered elsewhere), `MIGRATED` (live Multica mirror carries
the work), `OPEN-RESIDUAL` (genuinely open; a named residual must still be finished),
`DEFERRED-OWNER` (needs an owner decision/permission/credential).

## Ledger

| # | Source | Status 2026-11-11 | Archive record | Multica home | Disposition | Evidence / residual |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | KOMAA-1004 Chat with CTO | nonterminal (chat) | absent | — | TRANSIENT | Chat record; do not migrate or rerun. **Gap:** chat-origin records were excluded from the archive (archive `origin_kind` set has no chat kind), so no archived copy exists. |
| 2 | KOMAA-1008 Chat with Harness Agent | nonterminal (chat) | absent | — | TRANSIENT | Same gap; "Harness Agent" persona is retired. |
| 3 | KOMAA-1014 Chat with Engineer | nonterminal (chat) | absent | — | TRANSIENT | Same gap. |
| 4 | KOMAA-1015 Chat with Designer | nonterminal (chat) | absent | — | TRANSIENT | Same gap. |
| 5 | KOMAA-1016 Chat with Lifecycle Ops | nonterminal (chat) | absent | — | TRANSIENT | Same gap. |
| 6 | KOMAA-1017 Chat with UI QA | nonterminal (chat) | absent | — | TRANSIENT | Same gap. |
| 7 | KOMAA-1018 Chat with Email Creative | nonterminal (chat) | absent | — | TRANSIENT | Same gap. |
| 8 | KOMAA-1490 Chat with Hermes Test | nonterminal (chat) | absent | — | TRANSIENT | Same gap; Hermes Test role retired. |
| 9 | KOMAA-1600 Chat with CHO | nonterminal (chat) | absent | — | TRANSIENT | Same gap. |
| 10 | KOMAA-966 Chat with MCP Engineer | nonterminal (chat) | absent | — | TRANSIENT | Same gap. |
| 11 | KOMAA-1494 Named MCP run-scoped Wiki/Skills + 401 rejection | blocked | yes (blocked) | ZARI-104 (archival, blocked) | SUPERSEDED | Paperclip Named-MCP/Wiki/Skills surface is retired: `multica-mcp` exposes 184 native CLI tools and no Wiki/Skill operation; all 200 Paperclip ops are `ARCHITECTURALLY_INCOMPATIBLE`. Run-scoped projection is delivered natively by per-agent Hermes MCP projection (`5d9c29d`, PR #98) and denial is covered (`tests/server.test.mjs:39` → 401). Wiki content survives as `docs/knowledge/paperclip-archive/` (historical_only). |
| 12 | KOMAA-1496 Real-agent Hermes Gateway E2E | blocked | yes (blocked) | ZARI-106 (archival, blocked) | SUPERSEDED | Real-agent E2E delivered: 14/14 named role profiles with real RepoWise + own-bank Hindsight tool results (ZARI-60/76), Opik traces (ZARI-75/91), post-deploy canary on `5d9c29d` (ZARI-131). |
| 13 | KOMAA-1497 Hermes release exact-SHA + rollback | blocked | yes (blocked) | ZARI-105 (archival, blocked) | OPEN-RESIDUAL | Deploy lane works (PR #98 → host sync `5d9c29d` → ZARI-131 canary; multica-mcp PR #99 live per ZARI-134), but the release gate still reads Paperclip `issue_work_products`/`heartbeat_runs` and multica-mcp's managed `/health` probe is unfixed (ZARI-111 blocked). Residual needs a CHO-approved Multica-native gate contract + health-probe fix. |
| 14 | KOMAA-1513 GitHub App → Git-backed Coolify auto-deploy E2E | blocked | yes (blocked) | ZARI-109 (archival, blocked) | SUPERSEDED | Git-backed Coolify auto-deploy is the live lane (`multica-mcp` README: base_directory `/multica-mcp`, watch path `multica-mcp/**`, build on push to `main`); PR #98/#99 shipped through it and were verified live. Owner residual (not this issue): App lacks `workflows:write`/rulesets and `main` is unprotected (ZARI-137 §1). |
| 15 | KOMAA-1512 Native run-scoped MCP bridge + readiness gate | in_review | yes (in_review) | ZARI-99 (archival, blocked) | SUPERSEDED | Bridge equivalent merged as PR #98 (`5d9c29d`, per-agent run-scoped projection lock), independently reviewed diff-only in ZARI-127, regression-protected by ZARI-132/PR #99. |
| 16 | KOMAA-1518 Hermes Test E2E | nonterminal | absent | — | SUPERSEDED | Hermes Test is not in the 14-role roster (ZARI-4); per-role canaries ZARI-60..76 replaced a gateway-wide single-agent E2E. Low confidence: no source record (absent from archive). |
| 17 | KOMAA-1549 Hindsight: migrate 14 isolated banks + validate profiles | blocked | yes (blocked) | ZARI-103 (archival, blocked) | MIGRATED | All 14 role-isolated self-hosted banks are live and are exercised by real own-bank recalls (ZARI-80..93); role-profile isolation verified (ZARI-55). Residual DEFERRED-OWNER: source→target content parity cannot be proven without Vectorize export credentials (ZARI-137 §3). |
| 18 | KOMAA-1553 Execute 14-bank migration + Hermes E2E | blocked | yes (blocked) | ZARI-108 (archival, blocked) | MIGRATED | Execution completed in Multica (see row 17); the Paperclip-era sequencing (blocked by KOMAA-1512) is void. Same parity residual, owner-held. |
| 19 | KOMAA-1585 Govern technical questions at Paperclip MCP boundary (PR #40) | blocked | yes (blocked) | ZARI-101 (archival, blocked) | SUPERSEDED | The defect class (agent-boundary decision/question side-channel) cannot recur: `multica-mcp` is a stateless caller-token CLI adapter with per-call authorization by Multica and no ask/decision tool in its 184-tool catalog. |
| 20 | KOMAA-1605 Opik MCP OAuth E2E + PR #51 promotion | blocked | yes (blocked) | ZARI-102 (archival, blocked) | SUPERSEDED | `multica-mcp` does not implement OAuth by design ("the installed Multica version is not a generic OAuth authorization server"), so the OAuth requirement is void; Opik telemetry is delivered natively (ZARI-75/91, ZARI-33). Residual DEFERRED-OWNER: Opik MCP agent access needs a CF Access service token (ZARI-137 §4). |
| 21 | KOMAA-1606 Run-scoped GitHub App access for CTO/CHO | in_progress | yes (in_progress) | ZARI-98 (archival, blocked) | DEFERRED-OWNER | App read path demonstrably works (exact-SHA review ZARI-110; PR reviews ZARI-118/123/127). Missing capability is App-level `workflows:write` + rulesets/branch protection — an owner action on App 5398752 (ZARI-137 §1). Not superseded: the gap is real. |
| 22 | KOMAA-1594 Review-to-rework issue-run recovery | in_progress | yes (in_progress) | ZARI-97 (archival, blocked) | SUPERSEDED | The Paperclip native review object it repaired does not exist in Multica (no review operation in the CLI catalog); rework is routed by `in_review` status + assignee + comment threads, exercised in ZARI-118/123/127. Disclosed parity gap: Multica has no native typed approve/changes_requested gate. |
| 23 | KOMAA-1556 Empirical agent delivery E2E (both lanes) | in_review | yes (in_review) | ZARI-100 (archival, blocked) | OPEN-RESIDUAL | Half-delivered: Hermes/host lane proven (ZARI-131, ZARI-132 live). Product lane and the readiness endpoint still depend on the Paperclip-DB release gate; `app/**` is outside the agent edit boundary. Needs owner approval of the Multica-native gate contract + one low-risk product issue (ZARI-137 §2). |
| 24 | KOMAA-1538 Production family rollout + eight-character lineup E2E | blocked | yes (blocked) | ZARI-95 (CHO, blocked) | OPEN-RESIDUAL | One precondition cleared since the source issue: ComfyUI MCP is deployed and secured with passing CPO/Mascot canaries (ZARI-114/115/135/136). Still open: accepted Kuna pilot, exact approved image SHAs, independent CPO digest-bound review, production publication path. |
| 25 | KOMAA-1586 Wilk (ENTJ) mascot candidate + CPO acceptance | blocked | yes (blocked) | ZARI-96 (Mascot Designer, under ZARI-95) | OPEN-RESIDUAL | Same precondition set as row 24; generation/deploy must not start before the Kuna pilot and ComfyUI projection are confirmed. |
| 26 | KOMAA-1464 Plasmic MCP token-redaction fix | nonterminal | absent | ZARI-113 (specialist MCP parity, blocked) | DEFERRED-OWNER | Plasmic MCP is healthy as a service but not published on the agent loopback; scope, port and token wiring are an owner decision (ZARI-113, ZARI-137 §5). Token redaction must be a precondition of any publication. No duplicate issue created. |
| 27 | KOMAA-1559 PR work-product SHA regression coverage (PR #33) | in_review | yes (in_review) | ZARI-107 (archival, blocked) | OPEN-RESIDUAL | Work products are a Paperclip-only concept (`issue_work_products`); `multica-mcp` exposes no equivalent operation. The requirement therefore needs an explicit CHO decision — implement a Multica PR-linkage regression suite, or retire the requirement — not silent resurrection of Paperclip tests. |
| 28 | KOMAA-797 Public MCP AddComment 500 | nonterminal | absent | ZARI-134 (backlog) | SUPERSEDED | The public MCP it reported against (`paperclip-mcp`) is no longer the public surface; `multica-mcp` is live and verified at `ad0cf80` (ZARI-132/134) and exposes `multica__issue__comment__add`. Residual probe: one authenticated `comment.add` call belongs in the ZARI-134 e2e canary rather than a resurrected Paperclip issue. |
| 29 | KOMAA-252 Disable unnecessary agent tools | nonterminal | absent | — | SUPERSEDED | Intent is enforced structurally now: per-agent role-scoped MCP projection (PR #98 `5d9c29d`) replaced the broad shared tool surface (ZARI-40/54/60). Low confidence: no source record (absent from archive, cancelled-era number). |

## Totals

TRANSIENT 10 · SUPERSEDED 10 · MIGRATED 2 · OPEN-RESIDUAL 5 · DEFERRED-OWNER 2 = 29.

## Findings that change later work

1. **Archive gaps are real, not cosmetic.** 14 of 29 keys have no archived metadata, and the
   archive's `origin_kind` set proves chat-origin records were excluded wholesale. Any future claim
   that "Paperclip history is archived" must be scoped to non-chat records.
2. **Neither Paperclip nor this ledger is a work queue.** Every genuinely-open item already has a
   blocked Multica mirror (ZARI-95..109) or an owner blocker in ZARI-137; promoting them requires the
   owner decisions listed there, not a rerun of Paperclip work.
3. **The cutover retired capability, not defects.** GitHub App write scope, the product release gate,
   Hindsight source parity, Opik MCP access and specialist MCP publication are the five real residuals;
   the rest of the Paperclip nonterminal set is superseded by delivered Multica equivalents.
