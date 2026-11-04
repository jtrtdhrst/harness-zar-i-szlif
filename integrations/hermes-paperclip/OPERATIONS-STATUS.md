> **Documentation-only main publication.** The source architecture, tests, hashes and admission/release gates below describe a candidate from [PR #36](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/36) unless explicitly called historical production evidence. Publishing this document in `main` does not publish the adapter code or certify Hermes production readiness. For any command referring to receiver/overlay source, check out exact, reviewed PR code SHA; do not run it from `main` and assume matching files exist.

# Hermes ↔ Paperclip — source, security, E2E and release runbook

**Document owner:** Harness Engineer (implementation); CTO (independent source/security review); CHO (DAG, promotion and production release).
**Last verified baseline:** 2026-11-04, UTC. This is an evidence snapshot, NOT a live health monitor.
**Scope:** `miloszspyrka-code/harness-zar-i-szlif`; Paperclip Hermes adapter; Hermes v0.22.5 receiver; native Named MCP; Hindsight; Opik; GitHub/Coolify.
**Release verdict at baseline:** **NO-GO for production Hermes cutover**. Adapter security review has passed; the issuer-bound end-to-end run and deployment gates have not.

## 1. Truth sources and precedence

1. **Paperclip first-class issue fields** decide status, dependencies and native CTO/CHO review. Comments are evidence, not native approval.
2. **GitHub branch HEAD, checks and image digest** determine which source was actually built. README claims and historical comments cannot substitute for exact-SHA CI.
3. **Production Coolify + process + traces + issuer audit** determine what actually runs. An isolated image or HTTP 200 health check does not prove an authorized Paperclip run.
4. **No secrets** in Markdown, Git objects, prompts, stdout/stderr, error objects, traces, test fixtures based on real tokens, or issue/PR comments. Only redact/aggregate results. This document never authorizes copying production keys.

This runbook is the **single current integration-state entrypoint** (an evidence snapshot, not a substitute for live readback). Documentation ownership and use:

| Document | Purpose | Release authority |
| --- | --- | --- |
| **This `OPERATIONS-STATUS.md`** | Source map, identity/security contract, current evidence baseline, acceptance matrix, rollback and release procedure | Checklist only: requires native CTO/CHO decisions and live production evidence |
| [`gateway/RUN_SCOPED_RECEIVER_CANDIDATE.md`](gateway/RUN_SCOPED_RECEIVER_CANDIDATE.md) | Version-pinned Hermes API receiver, private run-scoped session registry, implementation and test entrypoints | Component specification; never production approval |
| [`paperclip-core-overlay/README.md`](paperclip-core-overlay/README.md) | Paperclip adapter patch for the pinned image, upstream/Core boundary, build and TypeScript/Vitest evidence | Component specification; never production approval |
| [`README.md`](README.md) | 2026-11-01–02 harness/pilot results and retired Hermes Test evidence | **Historical only**; its old checklist is superseded |
| [`GATEWAY_PRODUCTION_READINESS_2026-11-02.md`](GATEWAY_PRODUCTION_READINESS_2026-11-02.md) | Earlier Gateway/profile operational baseline | **Historical only**; its readiness and PR references are dated |
| Paperclip Wiki: `wiki/concepts/hermes-paperclip-run-scoped-e2e.md` | Discover this Git-tracked runbook through Paperclip Wiki/issue context | Discovery pointer; do not fork the runbook into Wiki |

**Publication rule:** This runbook is independently published to `main` as *documentation only*. Adapter, Hermes runtime receiver, patches, tests, Dockerfiles and workflows remain candidate material in PR #36 and are **not** assumed to exist in `main`. This documentation promotion does **not** authorize PR #36 merge, production deployment or agent cutover. Recheck actual code PR HEAD, its exact-SHA CI and independent native CTO/CHO review before any code promotion.

The PR history is retained as evidence; obsolete local SHA snapshots are not the current state.

## 2. Source map: keep the two adapter patch baselines distinct

| Component | Exact source or path | Purpose |
| --- | --- | --- |
| Paperclip adapter worktree | Paperclip issue `KOMAA-1564`; branch `KOMAA-1564`; approved commit `792598741832c31d91d74c8de9e787639944d13e` | Implement in `packages/adapters/hermes/**` only; never push to `paperclipai/paperclip` main |
| **Paperclip overlay candidate (PR #36; NOT in `main`)** | `paperclip-core-overlay/overlay.patch` plus `adapter-runmcp-tests.patch` | Applies to pinned `ghcr.io/paperclipai/paperclip:2026.1023.0`, with independently merged native Core review recovery from PR #43 |
| Historical adapter candidate | `gateway/adapter-runmcp.patch` | Diff relative to earlier adapter source `4d90f3bc8`; **NOT applicable as the deploy patch against the pinned image** |
| Image assembly (PR #36 candidate only, not published in `main`) | `paperclip-core-overlay/Dockerfile` and workflow `.github/workflows/hermes-paperclip-adapter-overlay.yml` | Root-repository Docker build context, source hashes before/after both patches, focused tests/typechecks, compiled server runtime |
| Hermes receiver (PR #36 candidate only, not published in `main`) | `gateway/install_run_mcp.py`, `gateway/run_mcp.py`, `gateway/Dockerfile` | Pinned Hermes v0.22.5 source, private run-scoped MCP receiver, admission/cleanup and profile-bound routing |
| Native Core fix | `integrations/paperclip-core-review-recovery/overlay.patch` | Existing PR #43 (merged); preserve exactly; do not reimplement in the Hermes adapter |
| Opik role segmentation | PR #39 (open at baseline) | Must be independently reviewed and verified before relying on its production claims |
| Service promotion policy | PR #41 (merged at baseline) | Per-service explicit promotion; do **not** globally assume every merged `main` change automatically deploys |

The approved PR #36 **code baseline** before this documentation-only edit was
`d6a6f5455f9732b17ba00dc163c4c985ca9627ff` on branch
`KOMAA-1512-receiver-20261104`. It was **open and unmerged** when recorded.
Subsequent documentation commits may change PR HEAD while leaving adapter source bytes unchanged.
For every further build or reviewer decision, re-read the new PR HEAD and its checks.

Pinned Paperclip image: `ghcr.io/paperclipai/paperclip:2026.1023.0`.
Adapter `execute.ts` SHA-256 on approved Paperclip worktree and the assembled
pinned-image candidate after overlay:
`977e6ecfc457c330b8bc59e020456ca3361aebe877b065d4878573cd3cae0578`.
The image Dockerfile checks preimage
`e3593d03d40b37b215d68342c8d615d26014bf5892eef79151b6153737764701`
and the above postimage SHA-256. A mismatch is **STOP**, not a reason to bypass the checksum.

Hermes base: `nousresearch/hermes-agent:v0.22.5`;
upstream source pin `bf0203a794a07aac3ff764972ab9087baa4e4f4e`.
Receiver installer checks pinned upstream `api_server_runs.py` source SHA-256
`a9c3b02e51407ca30fc948753149984c0ec75dcc047763cf75a356c1baaba466`.

## 3. Acceptance ledger — observed status at 2026-11-04 baseline

| Gate | Native task | Current decision | Remaining evidence / blocker |
| --- | --- | --- | --- |
| **H01 adapter security** | **KOMAA-1564** | **DONE; independent CTO `approved` at 2026-11-04 19:14:01 UTC** | Code/source accepted; this is **not** a release approval |
| **H02 integration + admission** | KOMAA-1512 | **IN_PROGRESS; native review `changes_requested`** (readback 2026-11-04 22:17 UTC); prior run recorded cancelled/recovery | Resolve review/recovery in native Paperclip, then prove issuer-bound admission, cleanup, concurrency, replay/expiry and real MCP calls |
| **H05 Named MCP access** | KOMAA-1494 | BLOCKED by KOMAA-1512 | Positive Wiki + Skills from real authorized Paperclip issue/run; negative issuer tests |
| **Agent E2E** | KOMAA-1496 | BLOCKED by KOMAA-1494 | Real Hermes issue run, own-bank Hindsight readback, cross-bank denial, correlated native Opik |
| **GitHub/release authentication** | KOMAA-1513 | BLOCKED by KOMAA-1512 | Approved existing GitHub App from intended agent/deploy runtime, canary push/PR, immutable artifact mapping, forbidden repo denial |
| **Production promotion** | KOMAA-1497 | BLOCKED by KOMAA-1496 and KOMAA-1513 | CHO/CTO review, controlled merge, exact image digest to Coolify, health, rollback, canary and cohort rollout |

**Five principal remaining issue deliveries after H01**:
`KOMAA-1512`, `KOMAA-1494`, `KOMAA-1496`,
`KOMAA-1513`, `KOMAA-1497`.
The actual number of commands or days is **not** inferable from the issue statuses.
This is a causal DAG, not five independent parallel tickets.

**H02 execution/review readback — 2026-11-04 (not an unattended live monitor):**
Native `KOMAA-1512` is `in_progress`, but its first-class
`executionState.status=changes_requested`, `blockedBy=[]`, and
`executionBlocker.cause=legacy_execution_requires_reconciliation`
for cancelled run `2ba4171b-4421-40d2-877f-9ed629f082bd`.
A prior eligibility readback had returned
`false_progress_no_issue_run` / `blocked_by_1` while H01 was done.
That was a **historical snapshot**, not evidence that those specific blockers
still exist. CHO must inspect live issue, reviewer decision, execution recovery
record and actual run before deciding the next first-class repair; do not force-wake,
erase reviews, mark a cancelled run as PASS or infer completion from
`in_progress`. The canonical acceptance tests in section 6 are still required.

Historical `KOMAA-1493` and `KOMAA-1495` are **cancelled**;
do not make the retired Hermes Test or Release Manager agents mandatory signoffs.
Existing PRs #18 and #28 are open at this baseline; assess overlapping changes
before merging any adapter, validation or rollout implementation.

## 4. H01 security validation — immutable evidence (approved)

- Paperclip worktree approved commit:
  `792598741832c31d91d74c8de9e787639944d13e`,
  clean status, changed adapter files limited to `packages/adapters/hermes/**`.
- Focused Vitest **114/114 PASS**, adapter TypeScript **PASS**,
  `git diff --check` **PASS** on the approved issue-owned source.
- Actual pinned Paperclip image after canonical overlay:
  `git apply --check` for the main adapter patch and tests **PASS**;
  focused Vitest **108/108 PASS**, adapter TypeScript **PASS**.
  The two counts differ because they are built on different test-file bases.
  The resulting actual adapter implementation `execute.ts` matches by SHA-256.
- Fail-closed redirect policy: JSON requests (including poll/stop), SSE GET and
  **POST `/v1/runs`** use `redirect: "error"`. Synthetic 307 and 308
  test plus a real localhost Node HTTP server: redirected target received
  **zero** calls, and synthetic bearer was absent from result/log/error output.
  This proves the tested redirect case, not every conceivable secret lifecycle path.
- URL normalization tested for `/p/cho`, `/p/cho/v1`,
  `/p/cho/v1/`: no `/v1/v1/` duplication; create/events/poll/stop/final
  routes covered.
- **Exact old PR HEAD CI: 3/3 successful**:
  [Hermes Gateway 41892513960](https://github.com/miloszspyrka-code/harness-zar-i-szlif/actions/runs/41892513960),
  [Paperclip MCP 41892514008](https://github.com/miloszspyrka-code/harness-zar-i-szlif/actions/runs/41892514008),
  [unified adapter overlay 41892514274](https://github.com/miloszspyrka-code/harness-zar-i-szlif/actions/runs/41892514274).
- Independent CTO native review on `KOMAA-1564`: **approved**,
  source-only, after earlier changes-requested cycles.
  [Evidence in PR #36](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/36#issuecomment-6639502714).

**Do not label the synthetic 307/308 tests, scope registry tests, or build
health checks as real credential lifecycle E2E.**

## 5. Run-scoped trust and credential contract

1. Paperclip creates a short-lived, issue/run/agent-bound grant from its
   authorized issuer. The adapter obtains actual `runtimeMcp.getServers()`
   and **must not** accept administrative `payloadTemplate.paperclip_run_mcp`.
2. The adapter requires `sessionKeyStrategy=run`, a UUID run and named
   HTTPS profile route. It sends POST to the profile's `/v1/runs` using the
   **matching profile API_SERVER_KEY**; request headers include
   `X-Paperclip-Run-Id`, `X-Hermes-Session-Key: paperclip:run:<UUID>`,
   and the run-bound idempotency key.
3. A private request field `paperclip_run_mcp` contains
   `version`, `company_id`, `agent_id`, `issue_id`, `run_id`,
   `profile`, `scopes`, `expires_at` and an array of HTTPS MCP
   server descriptions, each with ephemeral opaque `token`.
   **Never include this field in an LLM message, log or persisted profile**.
4. Hermes receiver authenticates the named-profile route and validates exact
   header/body identity. It strips the field before durable state, prompt,
   room/handoff and Opik processing; registers only private session-local MCP
   tools during that run and cleans them on completion, cancellation and error.
5. The endpoint allowlist permits only operator-controlled HTTPS destinations
   (default `https://paperclip-mcp.zariszlif.pl/mcp` or an explicit narrow
   `HERMES_PAPERCLIP_MCP_URLS` allowlist). No client grant may broaden it.
6. **The MCP issuer validates each actual tools/call**. Headers, UUID,
   profile key, expiry written by the client and a successful `tools/list`
   are insufficient by themselves to prove authorization. A revoked, expired,
   foreign-agent or foreign-run grant **must fail closed at tools/call**.
7. No `fetch` redirect is allowed when credentials may be present.
   No `curl -L`, verbose bearer dumps, ad hoc shared admin key,
   copied secret from a different profile or silent retry on an untrusted host.

## 6. The remaining E2E acceptance matrix (evidence, not assumptions)

| Case | Expected result | Current evidence |
| --- | --- | --- |
| Named profile API key missing / invalid | 401 or deny, no run | Earlier isolated synthetic negatives only |
| Missing/malformed/foreign profile grant | 403, no run | Local receiver validation / seam tests; production issuer path unverified |
| Valid **Paperclip-issued** grant | Accepted only on its exact run/profile; real `tools/list`, `tools/call` | **PENDING** |
| Native Wiki search/get and Skills list/get | Authorized output with version/marker, correct Paperclip run UUID | **PENDING** |
| Wrong agent, run, company/profile, missing, expired, revoked grant | Explicit denial, no protected data leak | **PENDING real issuer** |
| Concurrent runs and cancelled/failed run cleanup | No credential crossing or stale MCP registry | Local seam tests; real concurrent sessions **PENDING** |
| Native Hindsight own-bank retain + independent-session recall | Exact stored memory ID and readback | **PENDING** |
| Hindsight wrong-bank request | Denied with no returned confidential fact | **PENDING** |
| Native Hermes Opik trace for the same run | `thread_id` and `metadata.task_id` align with exact `paperclip:run:<UUID>`, model/tool/usage spans | **PENDING** |
| GitHub App + artifact chain | Authorized canary branch/PR, unauthorized repo denial, pinned commit → image digest → Coolify deployment | **PENDING full runtime proof** |
| Production canary + rollback | Health, actual tool path, event/run trace, safe reversal, no data loss | **PENDING** |

For every case, record **without secrets**: Paperclip issue ID, real run UUID,
source SHA, image digest, profile name, tool name, HTTP status/deny reason,
time, trace IDs, expected vs observed result, CI job URL and reviewer decision.
The negative matrix must use invalid/fabricated identities only where possible;
for revoked/expired tests, mint and revoke legitimate *test* grants.

## 7. Reproducible focused checks (no production mutation)

In the **isolated issue-owned Paperclip source worktree** (never shared dirty
checkout), after verifying `git status --porcelain` is clean:

```bash
git rev-parse HEAD
git diff --check origin/master...HEAD
pnpm exec vitest run packages/adapters/hermes/src/gateway/server/execute.test.ts
pnpm --filter @paperclipai/hermes-paperclip-adapter typecheck
sha256sum packages/adapters/hermes/src/gateway/server/execute.ts
```

In the **harness repository root** use the *current checked-out PR revision*
for the unified image. CI uses the root build context and file:

```bash
git rev-parse HEAD
docker buildx build --load --progress=plain \
  -f integrations/hermes-paperclip/paperclip-core-overlay/Dockerfile \
  -t hermes-paperclip-reviewed-candidate:local .
```

The Dockerfile pins base/result bytes, applies PR #43 Core review recovery and
the Hermes adapter once, runs focused tests and typechecks, and checks the
compiled server runtime. A local build does **not** authorize promotion.
No copies of real keys should be supplied to these test jobs.

For the receiver, build from the service's version-pinned `gateway/Dockerfile`,
then run its Python unit/admission/registry tests with **synthetic credentials**,
in an isolated container. The source installer must abort on mismatched upstream
SHA, rather than continuing with potentially incompatible code.

## 8. Production runbook — controlled actions after gates pass

**Before each irreversible promotion:** re-read Paperclip source issue and
first-class approval, compare GitHub PR HEAD with tested commit, inspect CI,
review deployment target and image digest, retain rollback configuration,
and ensure only intended service/profile is affected.

1. **H02:** reconcile candidate sources and both endpoints without duplicating
   existing patches. Verify real profile-key binding, scoped admission, concurrency,
   cleanup, expiry/replay policy with issuer-generated *test* grants. CTO decides
   whether the exact approved artifact is safe to promote to the next stage.
2. **H05:** start an **actual issue-scoped Paperclip run** through the named
   Hermes profile, not a CLI-only `local-*` trace. Prove native Wiki and Skills
   with live permissions and full negative access matrix. Preserve redacted
   evidence and independent reviewer decision.
3. **KOMAA-1496:** use the **same real run UUID** to correlate Hermes-native
   Hindsight retain, subsequent recall and cross-bank denial with native Opik
   spans. This includes model/provider and tool/usage, not only Gateway health.
4. **KOMAA-1513:** verify existing approved GitHub App credentials from the
   actual Paperclip agent and deployment runtime. Exercise a harmless authorized
   branch push/PR, unauthorized repository denial and exact source-SHA/image
   promotion mapping. Do not invent an App or distribute broad shared tokens.
5. **KOMAA-1497 (CHO):** obtain native CHO/CTO approval, merge **reviewed**
   source through the per-service promotion policy (not global main-only),
   build immutable image, record digest, deploy via existing GitHub → Coolify,
   then read back **actual** production SHA/digest, health and authorized run.
   Perform and record safe rollback test.
6. **Cohort migration:** Wave 0 Designer; Wave 1 COO + UI QA;
   Wave 2 CEO + CMO + Mascot Designer + Lifecycle Ops;
   Wave 3 remaining Engineer + MCP Engineer + Email Creative + CPO +
   Harness Engineer + CTO + CHO. Preserve all other adapters and role-specific
   memory banks unchanged until each target cohort passes its own real run,
   Wiki/Skills, own-bank recall and Opik checks. Confirm current agent roster
   and model routing *before* executing any wave; this is a plan, not a claim
   that the roles have migrated.

**Immediate STOP/rollback conditions:** token/prompt/log leak, unsupported
redirect, patch/SHA drift, foreign-run grant accepted, data leakage across
roles/banks, incomplete native trace correlation, wrong model/profile,
failing checks, missing native reviewer decision, or deployed digest mismatch.

## 9. Documentation maintenance and closeout

- This runbook is **source-controlled documentation on PR #36**, not a claim
  that it is already merged to `main` or deployed.
- Keep code fixes in their **correct** source with regression tests; do not
  edit server/Core or three existing Cloudflare production Workers from H01.
- On every new source commit update the exact-SHA ledger **and** re-run
  checks; do not transplant an old `SUCCESS` label to the new HEAD.
- Do not mark H02/H05/E2E as done on static documentation. First-class issue
  status must follow production receipts and independent review.
- Record final proof in Paperclip issue(s), linked PR(s), CI artifact links,
  Coolify deployment digest and Opik trace references (redacted).
- Close only after verified readback, rollback receipt and CHO signoff.
