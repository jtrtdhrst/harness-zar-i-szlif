---
title: Paperclip local architecture — upstream master divergence and deployed overlay registry
type: concept
tags: [paperclip, architecture, upstream-divergence, cho, harness, core, mcp, hermes, docker, source-of-truth]
updated: 2026-11-07
---

# Paperclip local architecture vs upstream — canonical agent source of truth

**Audience/maintainers:** CHO (architecture owner/release acceptance), Harness Engineer (implementation/verification). **Purpose:** make the locally modified Paperclip architecture available at session start without repeated source archaeology. **Scope:** code, image, MCP/sidecars, Git/release and deployment boundaries. This is NOT an incident tracker, an instruction to merge, or evidence that every planned patch is deployed.

**Required interpretation:** This is a **verified baseline snapshot** checked 2026-11-07, combined with permanent architecture contracts. When a different conversation/agent is changing the system concurrently, read immutable current live state before taking action and update THIS register on the same delivery. Do not overwrite or race an active worktree or production service. Source code and live image digest take precedence over documentation when they disagree; **fix the documentation in the same approved delivery**, rather than assuming upstream behavior.

## 0. Upstream identity: never call it `main`

- **Official upstream:** `https://github.com/paperclipai/paperclip`. Its current default development branch is **`master`** (NOT `main`), verified public `master` HEAD at this snapshot: `8812c1941d82d0f8960a2db272086cff57655cf0`.
- **Locally pinned base image for OUR Core:** `ghcr.io/paperclipai/paperclip:2026.1023.0`. The Harness overlay runbook identifies pinned upstream source commit `1b4c803816e82b0265c8422e1a804327a7ed8c54`. This is a frozen released baseline, **not** the live upstream `master`.
- **Owner's public fork:** `miloszspyrka-code/paperclip`, `master` was observed at `381b7638469b31d7c8c47a1329a9825ac4d61e3b`. It is a separate repository: do not infer it equals upstream master, production build, or the Harness overlay source. Read-only unless a narrowly authorized task explicitly owns writes.
- **Canonical local customization source:** private `miloszspyrka-code/harness-zar-i-szlif`. It contains Core patch/diff layers in `integrations/paperclip-core-review-recovery/` and `integrations/hermes-paperclip/paperclip-core-overlay/`; plus separate Paperclip MCP in `paperclip-mcp/` and Hermes receiver in `integrations/hermes-paperclip/gateway/`.
- **No safe blind upgrade:** upstream `master`, pinned base `2026.1023.0`, the owner's fork, Harness source SHA, built image ID, and actual running image ID are **six separate identities**. Before rebase or upstream bump, compare touched upstream files AND our exact patches against the NEW base; missing local function names in upstream `master` are hints, not formal semantic diff. Do not drop a custom behavior because upstream appears newer or because a commit was merged in Harness.

## 1. Runtime architecture and trust boundaries

```text
Paperclip agent (issue-scoped run; 14 configured actors)
  |
  +--> Paperclip Core (scheduler, issue DAG, reviewers, executions, DB, /api:3100)
  |       |  [CUSTOM image: pinned upstream 2026.1023.0 + selected Core overlays]
  |       +--> local OpenCode adapter (13 agents as-of snapshot)
  |       +--> Hermes gateway adapter inside Paperclip (1 Designer configured, ERROR)
  |                    |
  |                    +--> Hermes profile-specific HTTPS /v1/runs receiver (separate Coolify app)
  |                              +--> per-run Named MCP (Wiki/Skills)
  |                              +--> per-role Hindsight memory bank
  |                              +--> same-run Opik traces
  |
  +--> Paperclip MCP Gateway (SEPARATE container /mcp:3101)
          [CUSTOM Harness paperclip-mcp/mcp-gateway + src/*]
          +--> per-caller principal and run credential checks
          +--> Paperclip Core API (no shared board token substituted for agent)
          +--> issue fields, review/rework, workspaces, native GitHub App transport
          +--> authenticated external MCP clients; OAuth/transport edge

GitHub (owned product + Harness repos; custom review/release admission)
  +--> approved product main → ci-approved → Coolify product
  +--> per-service source/digest promotion → Coolify Core/MCP/Hermes as appropriate
```

**Do not conflate Core and MCP:** Core exposes scheduler/DB/issue lifecycle and executes adapters; the custom MCP sidecar exposes tool APIs, authorization/presentation and native workflow/Git operations and calls Core. A fix in `paperclip-mcp/src/p1-git.ts` DOES NOT automatically alter `server/src/services/issues.ts`; a Core image rebuild does not automatically update the MCP image. A successful `tools/list` proves neither native issue-scoped authorization nor Hermes/Hindsight/Opik execution.

**Database and volumes:** production Core uses existing Coolify Compose resource and persistent Paperclip volume. Never start a second mutable Core against the same production DB/volume. Paperclip MCP has its own persisted OAuth/state volume. Gateway and per-role Hermes profiles are separate components; preserve scoped secret/identity boundaries.

## 2. Exact deployed Core image — audited runtime, NOT a Git branch name

- **Coolify Core service:** `2omzqpy8dxgmhuwfbzo7bvvv` (Compose).
- **Running container:** `paperclip-2omzqpy8dxgmhuwfbzo7bvvv`.
- **Running image tag:** `local/paperclip-core-auth-denial:20261106`.
- **Running immutable Docker image ID:** `sha256:a04c97c849c5dfd11b4d42db14d44a04e00704fa418b2b0eb5cd90863412556d`; confirmed by Docker inspect and saved `/opt/paperclip-releases/core-auth-denial-20261106/candidate-image-id` at snapshot.
- **Actual final host build input:** `/opt/paperclip-releases/core-auth-denial-20261106/Dockerfile`; it starts FROM `local/paperclip-hermes-h03-reconciliation:20261106` (itself built FROM `local/paperclip-hermes-core-h03-candidate:833c507f-56204bc9`) and copies compiled/tested Core source files. Thus the CURRENT production image is **not** simply the `integrations/hermes-paperclip/paperclip-core-overlay/Dockerfile` built from latest Harness `main`.
- **Build source reproducibility caveat:** host-local intermediate image layers and copied sources exist; historical image labels such as `KOMAA-1564-Hermes-with-reviewed-PR43-Core` do **not** themselves establish the real build commit or equivalence to the latest repo. Maintain a source→patch hash→image digest release receipt. Do not rebuild FROM a mutable tag or replace production merely because CI is green.

### Verified changed-file inventory vs pinned upstream release (read-only Docker diff, 2026-11-07)

A direct content SHA-256 comparison was performed between the production container's `/app/server/src` and `/app/packages/adapters/hermes/src` versus a **transient, network-disabled** container from `ghcr.io/paperclipai/paperclip:2026.1023.0`. No production files were changed. Results: **2058 upstream source files, 2062 live files; exactly 13 changed/added, 0 removed inside these two scanned source roots**. This is the effective code-level delta for the scanned Core + Hermes adapter paths; it does **not** certify that every other file tree, compiled output or infrastructure sidecar is identical.

| File relative to `/app` | Status | Baseline SHA-256 prefix | Production SHA-256 prefix | Ownership / significance |
| --- | --- | --- | --- | --- |
| `packages/adapters/hermes/src/gateway/server/execute.ts` | modified | `e3593d03d40b37` | `c30d88b557b7c4` | run-scoped Hermes adapter + model routing |
| `packages/adapters/hermes/src/gateway/server/execute.test.ts` | modified | `5cd8988db80e10` | `32c877e8ce8dd6` | adapter regressions |
| `server/src/services/execution-blocker.ts` | modified | `bccaebea9d6252` | `7ec285484ef666` | H03 blocker and review continuation |
| `server/src/services/issues.ts` | modified | `b5b3066bd58587` | `1fe74c51a5e93d` | reviewer checkout |
| `server/src/routes/issues.ts` | modified | `641b3d9cb5e744` | `6631daa3d0ddf6` | reviewer route stage handling |
| `server/src/services/heartbeat.ts` | modified | `f3369d87010af5` | `6ce316dc1329` | execution continuation |
| `server/src/services/legacy-execution-recovery.ts` | modified | `dd5997b5f46e58` | `36046af06728` | Hermes pre-create authentication denial |
| `server/src/services/legacy-execution-recovery.test.ts` | modified | `c2cebf5763959b` | `44b0dc55f8cf` | legacy recovery regressions |
| `server/src/__tests__/issue-stale-execution-lock-routes.test.ts` | modified | `0c592a764ea7eb` | `664ba301371d06` | native reviewer admission test |
| `server/src/__tests__/issue-h03-false-progress-rework.integration.test.ts` | added | — | `6c3b400e8ea1c8` | H03 integration regression |
| `server/src/services/execution-blocker-rework.test.ts` | added | — | `52213e1e74340e` | issue unblock/rework regression |
| `server/src/services/execution-blocker-undispatched.test.ts` | added | — | `9d8d5a57e4dfcc` | pre-dispatch negative regression |
| `server/src/services/legacy-auth-admission.integration.test.ts` | added | — | `aeaf7e7660fe8a` | Hermes credential-denial regression |

**Important negative observation:** `server/src/services/recovery/service.ts` was **NOT** among these 13 changed files; it has the same pinned-base SHA prefix `c414df876e7d...` in the running Core, corroborating that the separate `review-wake-recovery.patch` is not deployed to this image. Source patch existence != running behavior.

**Reproduction (read-only):** hash `server/src` + `packages/adapters/hermes/src` in an ephemeral `docker run --rm --network none --entrypoint sh ghcr.io/paperclipai/paperclip:2026.1023.0` and independently inside the active Core container; compare sorted path→SHA maps. New builds should regenerate this inventory, store the machine-readable diff with the release evidence, and update the register, rather than trusting a manually remembered count.


### Effective local Core changes (compared with pinned upstream release)

| Change boundary | Runtime file(s) | Permanent source of change in Harness | Observable contract | Runtime 2026-11-07 |
| --- | --- | --- | --- | --- |
| Pre-dispatch review wait | `server/src/services/execution-blocker.ts` | `integrations/paperclip-core-review-recovery/overlay.patch`, PR #43 | Suppress stale blocker *only* when a cancelled run never dispatched; preserve real intervention and review | **PRESENT** in production `safeUndispatchedReviewHandoff` |
| Independent reviewer admission | `server/src/services/issues.ts`, `server/src/routes/issues.ts`, `server/src/services/heartbeat.ts` | `integrations/paperclip-core-review-recovery/reviewer-checkout.patch`, PR #57 | Correct reviewer+stage ownership, no foreign/self/stale checkout, return to executor on genuine rework | **SOURCE HASHES VERIFIED** in running Core; full native E2E is separate |
| Legacy changes-requested/H03 reconciliation | `server/src/services/execution-blocker.ts` | `integrations/hermes-paperclip/paperclip-core-overlay/reconciliation-overlay.patch`, plus host `/opt/paperclip-releases/hermes-core-h03-reconciliation-20261106/` | Resolve only precisely proven non-dispatched, historical blocked recovery without fabricating decision | **PRESENT** in production `safeAbortedLegacyReworkHandoff` |
| Hermes pre-create auth rejection | `server/src/services/legacy-execution-recovery.ts` and regressions | `integrations/paperclip-core-review-recovery/legacy-auth-admission.patch`; final host `/opt/paperclip-releases/core-auth-denial-20261106/` | Definitive pre-create authentication rejection is NOT post-dispatch uncertainty; still fail closed and preserve audit | **PRESENT** in production `confirmedHermesCreateAuthDenial` |
| Hermes run-scoped adapter | `packages/adapters/hermes/src/gateway/server/execute.ts` | `integrations/hermes-paperclip/paperclip-core-overlay/overlay.patch`, `model-routing.patch`, PR #36 | Exact Paperclip-issued run/profile MCP envelope, redirect denial, run binding, no bearer into model/log | **SOURCE HASH VERIFIED** in running Core; real grant E2E separately NOT VERIFIED |
| Lost native review wake replay | `server/src/services/recovery/service.ts` | `integrations/paperclip-core-review-recovery/review-wake-recovery.patch` | Replay exactly a skipped authorized pending review wake once, after lease release, not arbitrary retry | **NOT PROVEN DEPLOYED**: live file SHA equals the previously pinned preimage `c414df876e7df64e701a752513db8e5cf7365589294d50da0e1396788a9207db`; compiled-marker probe absent in live Core. Source file/merged PR ≠ deployed state. |

**Live SHA proof for critical effective files:**
```text
server/src/services/execution-blocker.ts             7ec285484ef6664321e9b2e6aba73eb2c0254554db703328f5a02d6169a960a0
server/src/services/legacy-execution-recovery.ts      36046af06728f6e800d5eb87289025014150b1a1b0ebe927290619fc7c2e7712
server/src/services/issues.ts                         1fe74c51a5e93d9323868425b5780273ce8790620787ed34c6c7f98c42d60bc5
server/src/routes/issues.ts                           6631daa3d0ddf679e00d4514b60beef654a5671a06e80855d4bd568f0833e125
server/src/services/heartbeat.ts                      6ce316dc1329f1d58d721994f409a30a0fc730691b93d43abf30a94f2bb41879
server/src/services/recovery/service.ts               c414df876e7df64e701a752513db8e5cf7365589294d50da0e1396788a9207db
packages/adapters/hermes/src/gateway/server/execute.ts c30d88b557b7c443b76ff52e77cff93fdea1427eae030cdc65563cc850d2b051
```

**Upstream `master` textual probe** against exact commit `8812c194...`: `safeUndispatchedReviewHandoff`, `safeAbortedLegacyReworkHandoff`, `confirmedHermesCreateAuthDenial`, and `execution-stage-lease-recovery` were absent in the corresponding upstream source files. This verifies those named local implementation markers have not been copied verbatim to the inspected upstream branch. It is **NOT** evidence that upstream lacks any functionally equivalent behavior; for upgrades run an actual source/behavior comparison and regression suite.

## 3. Separate Paperclip MCP customization — NEVER assume upstream Core API has it

**Coolify MCP service:** `gevr1m6rdj4t4fbhcjvqv8gg`. At snapshot its running image tag was `paperclip-mcp:gitops-active`, Docker image ID prefix `4574afec7fd6`. This is a SEPARATE image/release from Core. Canonical source `harness-zar-i-szlif/paperclip-mcp/`.

| Extension | Implementation | Why it exists / safety boundary |
| --- | --- | --- |
| OAuth Streamable HTTP edge | `paperclip-mcp/mcp-gateway/gateway.mjs`, `entrypoint.sh` | External `/mcp`, health/OAuth endpoints, stateful authorization transport; preserve existing secrets/volume |
| Caller identity, no ambient Board leakage | `mcp-gateway/principal.mjs` | Caller agent, Board and service principals are distinct; per-run JWT binding must match the caller. Never inject a gateway-owned Board principal for every agent |
| First-class issue relationships/execution | `src/issue-fields.ts`, `src/control-plane.ts` | Real issue DAG, native blockedBy/blocks, reviewer stages, interactions and policy, not comments/description text |
| Issue-owned workspace and GitHub transport | `src/workspace-native.ts`, `src/p1-git.ts` | Run-scoped workspace/branch ownership, authorized GitHub App permission and PR review/merge gating; no direct upstream public writes or broad personal PAT |
| Runtime tool projection, control layer | `src/tools.ts`, `src/effective-access.ts`, `src/live-verify.ts` | Tool discovery is not authorization; check effective principal, issue/run context, actual allowed/denied tool calls |
| Native reviewer/merge lineage | `src/p1-git.ts` and associated work-product logic | Merge must write back accepted head SHA, formal reviewer decision ID, merge commit SHA and merged status; open PR #33 alone does not prove actual deployed writeback. **Do not assume fixed** |
| Agent-assisted file ingress | `mcp-gateway/chatgpt-image.mjs`, `paperclip-mcp/docs/chatgpt-image-ingress.md` | ChatGPT file handoff/ComfyUI with byte-exact SHA/receipt; not part of upstream Core |
| Per-service deployment authority | `ops/release-lanes.json`, `docs/RELEASE-POLICY.md`, `wiki/concepts/git-coolify-release-contract.md` | Paperclip MCP Compose/image, Core Compose/image, Hermes Git-backed candidate/production, Product `ci-approved` are different lanes, not a universal `main` promotion |

**Machine authority:** Core state machine and DB are the truth for issue policy, active runs and formal review. MCP may expose operations and add validation/transport, but cannot mint Core reviewer decisions or skip a Core denial. Rejected API writes (401/403/409/422) must not be converted to fabricated Board writes.

## 4. Hermes integration (distinct target and current configuration)

**Source:** `integrations/hermes-paperclip/gateway/{Dockerfile,run_mcp.py,install_run_mcp.py,...}` and the adapter overlays above. **Release/runbook:** `integrations/hermes-paperclip/OPERATIONS-STATUS.md`. **Coolify Hermes primary:** `2sganhxhhnioiqh4an9g2f4k`. **Candidate:** `hut52do8jdwumzdnaphtnmfp`. Different branches/images exist; do not equate a healthy Hermes container or merged Harness PR #36 with successful Paperclip issuance or a production cohort cutover.

**Target security chain:** native Paperclip issue + authorized live run → adapter sends authenticated `/v1/runs` to the correct named profile → receiver validates exact agent/issue/run/profile/grant and registers ephemeral Named MCP → Wiki/Skills positive and wrong agent/run/expired negative → isolated per-profile Hindsight bank read/write with cross-bank denial → Opik trace correlated to the same run → canary, rollback and promotion. Never forward MCP bearer into LLM prompts, global config, logs or another profile's bank.

**Observed agent settings at snapshot:** 14 total; Designer is configured `hermes_gateway` and reports `error`; other 13 agents are still `opencode_local`. This is runtime state, **not** a recommendation to start the migration from the document. Current run and rollout can change in other conversations; always fresh-read.

## 5. Native execution/review architecture — do not copy upstream defaults blindly

- Native DAG has **separate** hierarchy `parentId`, causal dependency `blockedBy/blocks`, assigned owner, `executionPolicy.stages`, live `executionState`, reviewer `decisionId`, and immutable Git work product. They are not interchangeable. A cancelled blocker is NOT automatically satisfied.
- Repo-specific independent review: **Harness changes → CHO** and **Product changes → CTO**. No default serial two-review queue and no self-review. Agent `changes_requested` returns to executor with original independent reviewer/stage intact.
- The owner-directed `maxReviewRounds=50` is an explicit **per-issue native policy setting**, NOT a patched global Core default. Upstream default 3 may remain for new tasks without the explicit override; correct via supported creation/review policy and readback, not a fictitious runtime constant. See `wiki/concepts/paperclip-agent-review-rework-no-human-escalation-20261106.md`.
- A persisted `in_progress` without a real bound run is not execution. A status flip is not a reviewer decision. A pushed PR is not a merged work-product update. Release identity needs `source SHA → accepted head SHA → formal review ID → merge SHA → built image ID → deployed image ID → live behavior/rollback`.
- GitHub account boundary: official `paperclipai/paperclip` is **read-only** for local agents absent explicitly scoped owner authorization. The existing GitHub App must not grant unreviewed writes there. Minimize Actions churn; no no-op pushes or duplicate PRs.

## 6. Canonical read order: zero repeated architecture archaeology

**Relevant session, on start:** load the attached `paperclip-local-architecture` company Skill (compact map of this page) and read this Wiki **only if deep source/architecture detail is necessary**. This replaces reconstruction across dozens of issues/comments. Then read just the affected file/runbook and the CURRENT immutable source/digest/issue state. No full historical log crawl or broad wiki scan.

| Question | First source |
| --- | --- |
| What is customized vs upstream? | THIS architecture register + attached Skill |
| Where are exact Core patches and Docker build? | Harness `integrations/paperclip-core-review-recovery/` + `integrations/hermes-paperclip/paperclip-core-overlay/`; host `/opt/paperclip-releases/` for actual deployed image provenance |
| How do review/issue/run/permissions work? | THIS page + `wiki/concepts/paperclip-agent-review-rework-no-human-escalation-20261106.md` + `paperclip-mcp/src/issue-fields.ts` / `workspace-native.ts` |
| How does custom MCP differ from Core? | Harness `paperclip-mcp/README.md` + `paperclip-mcp/mcp-gateway/principal.mjs` |
| How does Hermes integration actually work? | Harness `integrations/hermes-paperclip/OPERATIONS-STATUS.md` + gateway/adapter sources |
| What is in production NOW? | Docker inspect image ID, Core file hashes, Coolify specific UUID, Paperclip native issue/run/review, authenticated probes |
| How do we promote/roll back? | `wiki/concepts/git-coolify-release-contract.md`, `docs/RELEASE-POLICY.md`, affected per-service runbook and exact digest receipts |
| What failed last time? | Only if matching issue/fingerprint: `wiki/concepts/owner-change-delivery-and-open-defects-20261107.md` (INCIDENT LEDGER, **not architecture**) |

## 7. Required upkeep for ANY future change that diverges from upstream

For every custom Paperclip Core patch, MCP extension, new native execution behavior or service binding, CHO/Harness Engineer MUST update THIS architecture register and the affected versioned source README/runbook **in the same reviewed delivery**. Each change record must state:

```text
CHANGE_ID / issue; business rationale and why upstream does not suffice
UPSTREAM: repo + exact master/tag SHA; touched upstream path/hash
CUSTOM: owned repo + path + patch commit SHA + expected pre/post SHA + API contract
RUNTIME: Core/MCP/Hermes service UUID + build Dockerfile/layers + built image ID + live image ID
STATUS: SOURCE_ONLY | BUILT_CANDIDATE | DEPLOYED_VERIFIED | NOT_VERIFIED | RETIRED
TESTS: positive, negative/regression, CI exact SHA, issue-bound auth/interaction
IMPACT: consumer/role permissions, schema/volume compatibility, rollback and dependencies
REBASE: upstream drift/equivalence check, re-apply/reject rationale, migration strategy
OWNER/REVIEWER: Harness Engineer / CHO (or product Engineer / CTO for product)
DOCS: updated architecture register + versioned runbook refs
```

**Drift procedure:** (1) read actual upstream `master` head + pinned release SHA; (2) compute local changed-file inventory from overlays; (3) compare original/current file contents and semantics (not just function names); (4) classify `upstreamed / overlapping / still-custom / obsolete`; (5) rebase onto a NEW pinned candidate only in an isolated workspace; (6) run positive/negative tests, code review and canary; (7) update records and immutable deployment receipts. No direct forced merge/rebase of upstream into production or automatic deletion of a patch.

**Do not run source repair simply because this documentation is written**; another live conversation may own implementation. Documentation is durable architecture and discovery; explicit authorization, native review and source/release controls remain authoritative.
