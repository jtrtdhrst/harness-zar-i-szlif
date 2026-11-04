# Per-service approved artifact release policy

Owner/orchestrator: CHO. Independent native reviewer: CTO for release infrastructure; relevant CPO/CTO for product. **CI passing is not equivalent to independent review**. A recorded `changes_requested` decision stays binding until reworked and independently approved.

## Release immutable artifact, not an arbitrary branch

Approved **source commit and immutable image digest** (or Cloudflare version ID) is the release identity, never merely a branch name. Each service may have its own integration ref, candidate ref and approved release ref. **No system-wide requirement for production `main`.** A PR merge does not itself deploy a pinned-image service.

### Working product lane: preserve

`zar-i-szlif/main` → Product CI `validate-product` → fast-forward-only `ci-approved` → Coolify webhook → `https://panel.zariszlif.pl/__release.json` readback matching the exact SHA.

Real evidence from 2026-11-04: GitHub `main=ci-approved` and finished Coolify deployment = `7322f946a5a395db29fa95d14da1ea9037e30d7c`, production release readback same SHA, `/healthz` HTTP 200. Preserve `main` as *integration* branch and `ci-approved` as *release* branch for this service only. Do not directly deploy feature branches. The workflow's `promote-release` uses `needs: validate-product` and `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`; it pushes only fast-forward (no force).

### Manual pinned-image release lane for unverified Coolify services

The dated manifest `ops/release-lanes.json` inventories **4 Coolify applications and 26 Coolify services**. Six already classified lanes retain their specific release modes; the remaining 24 services/apps are explicitly represented as `other_resources`, with `promotion_state=hold` until verifiable provenance is obtained. Some are stopped or one-off and marked `inactive_no_promotion`. `running:healthy` does not prove source→image equivalence.

A release of a held service requires all of the following, per **specific Coolify UUID**, not a mass redeploy:

1. CHO identifies the exact intended repository and commit **or** upstream image source/version, build job/checks, immutable candidate digest, existing actual running digest, last known-good rollback digest, target environment and whether schema/data changes require backup.
2. Independent CTO native review approves the exact candidate and access/security implications. For ordinary product/UI changes use the configured independent issue reviewer; no needless extra human step.
3. An isolated canary passes smoke, negative authorization tests and source SHA ↔ immutable digest verification. A passing build, a mutable tag such as `latest`, and a health check alone are insufficient.
4. Authorized deployment of that *approved immutable digest* to that service only. Read back Coolify deployment ID/time, actual container ID/digest, live release revision/health and service-specific authenticated/unauthenticated smoke.
5. On failure, halt the promotion, roll back to the independently identified previously healthy digest, read back actual runtime and retain the previous serving release. Mark DONE only after the ledger includes source SHA, CI, independent approval, candidate digest, deployment time, actual runtime digest, authenticated/anonymous probes and rollback identifier.

For an upstream-pinned version, prove the registry digest; for locally built overlays, prove **both upstream base revision and actual overlay source SHA**. Do not infer harness provenance from upstream OCI labels. Paperclip Core is `ghcr.io/paperclipai/paperclip:2026.1023.0` sourced from `paperclipai/paperclip`, upstream revision `1b4c803816e82b0265c8422e1a804327a7ed8c54`, **not** a verified build of `miloszspyrka-code/paperclip`. Paperclip MCP overlay attestation belongs with existing PR #32. Multi-container services (Opik, Supabase, Hindsight, Plasmic etc.) require component-level digests and dependency-aware rollback, not just the representative image string in the manifest.

Hermes private canary is Git-backed at candidate branch `KOMAA-1512-receiver-20261104` with auto-deploy disabled. It is **not production**; Hermes production Coolify reports `degraded:unhealthy`. No cohort cutover without full authorized Paperclip run and Opik/Hindsight/Wiki/skills evidence.

### Three protected existing Workers: separate platform lanes

`stronaglowna`, `zariszlif-prawne`, and Cloudflare Worker `paperclip-mcp` are not Coolify services. Their existing deployment and version UUIDs are in `cloudflare_workers`. The Worker `paperclip-mcp` and Coolify service `paperclip-mcp` are two different resources. Review an exact immutable Worker version, verify source/CI/traffic assignment, smoke and previous-version rollback before controlled Cloudflare promotion. Current Git source commit provenance of all three Worker versions is **not verified**: all are on `hold`. Preserve them; no new or replacement Worker.

## Verified and unverified E2E gates — 2026-11-04

Full audited evidence: Paperclip native issue `KOMAA-1587`, document `release-e2e-attestation-20261104`.

| Gate | Evidence | Verdict |
| --- | --- | --- |
| Product PR/source→CI→release→Coolify→production exact SHA | [Product CI run 41834968103](https://github.com/miloszspyrka-code/zar-i-szlif/actions/runs/41834968103), Coolify and HTTPS exact SHA readback | **PASS (live)** |
| Missing `SOURCE_COMMIT` blocks product startup | Product CI negative container test | **PASS (real CI)** |
| Fast-forward allowed, divergent ref denied | Isolated temp Git repo reproducing `git merge-base --is-ancestor` | **PASS (isolated)** |
| Wrong expected release SHA rejected | Deliberately mismatched SHA in read-only production comparator | **PASS (read-only)** |
| Missing Coolify service/Worker, duplicate, fake approval, unreviewed promotion | `scripts/check-release-lanes.py --self-test` performs 11 fail-closed mutations | **Structural regression only** |
| Unauthorized feature-branch push bypass impossible at GitHub server | GitHub private-repo rulesets read returned HTTP 403 under current plan | **NOT VERIFIED / NOT ENFORCED** |
| Real failing production build preserves previous deployment | Deliberate destructive production failure not exercised | **NOT VERIFIED** |
| Real rollback of product or Hermes | Coolify previous image tags available; `current=null` in rollback-images response; no rollback executed | **NOT VERIFIED** |
| Source-overlay SHA ↔ running image digest for local MCPs | Upstream OCI revision labels are not overlay provenance | **OPEN / NO GO** |
| Hermes production end-to-end authenticated run | Coolify degraded and no safe cohort proof | **NO GO** |

A policy/schema check **cannot** prove GitHub server permissions, rollback, deployed image digest, canary success, authorization correctness or live source provenance. The CI job must never present such claims. `ops/release-lanes.json` is a dated inventory. Newly created resources require an authenticated Coolify/Cloudflare rescan and reviewed manifest update; the policy validator cannot discover them by itself.

Current GitHub private-repository rulesets API responded HTTP 403. Consequently CI + Paperclip approval provide process controls, **not unbypassable server-side branch protection**. Do not force-push `ci-approved`, manually overwrite approved image refs, silently redeploy unreviewed builds, or claim `DONE` for any service missing a live readback.

## Scope and owners

Keep all three existing Workers, secrets, production profiles and agent model allocations unchanged by this policy PR. No new Workers or global `main` rule. CHO owns reconciliation of existing KOMAA-1556/1559 and source PRs #28/#32/#36/#37/#39/#40, true native independent review decision, merge only after approval, post-merge CI and separately verified per-service deployments. This policy release is not authorization for a mass Hermes migration.
