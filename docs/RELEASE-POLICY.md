# Per-service approved artifact release policy

Owner/orchestrator: CHO. Independent native reviewer: CTO for release infrastructure; relevant CPO/CTO for product. **CI passing is not equivalent to independent review**. A recorded `changes_requested` decision stays binding until reworked and independently approved.

## Release immutable artifact, not an arbitrary branch

Approved **source commit and immutable image digest** (or Cloudflare version ID) is the release identity, never merely a branch name. Each service may have its own integration ref, candidate ref and approved release ref. **No system-wide requirement for production `main`.** A PR merge does not itself deploy a pinned-image service.

### Working product lane: preserve

`zar-i-szlif/main` → Product CI `validate-product` → fast-forward-only `ci-approved` → Coolify webhook → `https://panel.zariszlif.pl/__release.json` readback matching the exact SHA.

Real evidence from 2026-11-04: GitHub `main=ci-approved` and finished Coolify deployment = `7322f946a5a395db29fa95d14da1ea9037e30d7c`, production release readback same SHA, `/healthz` HTTP 200. Preserve `main` as *integration* branch and `ci-approved` as *release* branch for this service only. Do not directly deploy feature branches. The workflow's `promote-release` uses `needs: validate-product` and `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`; it pushes only fast-forward (no force).

### Manual pinned-image release lane for unverified Coolify services

The dated manifest `ops/release-lanes.json` inventories **5 Coolify applications and 26 Coolify services**. Seven already classified lanes retain their specific release modes; the remaining 24 services/apps are explicitly represented as `other_resources`, with `promotion_state=hold` until verifiable provenance is obtained. Some are stopped or one-off and marked `inactive_no_promotion`. `running:healthy` does not prove source→image equivalence.

A release of a held service requires all of the following, per **specific Coolify UUID**, not a mass redeploy:

1. CHO identifies the exact intended repository and commit **or** upstream image source/version, build job/checks, immutable candidate digest, existing actual running digest, last known-good rollback digest, target environment and whether schema/data changes require backup.
2. Independent CTO native review approves the exact candidate and access/security implications. For ordinary product/UI changes use the configured independent issue reviewer; no needless extra human step.
3. An isolated canary passes smoke, negative authorization tests and source SHA ↔ immutable digest verification. A passing build, a mutable tag such as `latest`, and a health check alone are insufficient.
4. Authorized deployment of that *approved immutable digest* to that service only. Read back Coolify deployment ID/time, actual container ID/digest, live release revision/health and service-specific authenticated/unauthenticated smoke.
5. On failure, halt the promotion, roll back to the independently identified previously healthy digest, read back actual runtime and retain the previous serving release. Mark DONE only after the ledger includes source SHA, CI, independent approval, candidate digest, deployment time, actual runtime digest, authenticated/anonymous probes and rollback identifier.

For an upstream-pinned version, prove the registry digest; for locally built overlays, prove **both upstream base revision and actual overlay source SHA**. Do not infer harness provenance from upstream OCI labels. Paperclip Core has **changed since the earlier upstream-image baseline**: current Coolify service runs `local/paperclip-review-recovery:4f05e290`, Docker image ID `sha256:ba2bf404be28f2ae5ee8a2a5785944280463f67f84fd52a3b20bda49d9af1855`. The base is upstream `ghcr.io/paperclipai/paperclip:2026.1023.0` at revision `1b4c803816e82b0265c8422e1a804327a7ed8c54`; the harness overlay source is merged PR #43 commit `4f05e2904b8663e096bf4f839f25d46767f18899`. These are three distinct identities. Running-image observation is real, but a reproducible overlay source-to-image digest build chain is **NOT VERIFIED**. Paperclip MCP overlay attestation belongs with existing PR #32. Multi-container services (Opik, Supabase, Hindsight, Plasmic etc.) require component-level digests and dependency-aware rollback, not just the representative image string in the manifest.

The newer `hermes-gateway-git-release-candidate` application (Coolify UUID `hut52do8jdwumzdnaphtnmfp`) runs a GitHub-backed harness `main` candidate with auto-deploy **to the isolated candidate only**. No public host ports and a separate `/opt/data` volume were observed, but the shared Coolify Docker network means complete isolation is **NOT VERIFIED**; this is neither Hermes production nor permission for automatic production promotion. A merge to harness `main` may trigger a rebuild of this candidate: verify the image/digest and runtime and do not call it a production release. Hermes private canary is Git-backed at candidate branch `KOMAA-1512-receiver-20261104` with auto-deploy disabled. It is **not production**; Hermes production Coolify reports `degraded:unhealthy`. No cohort cutover without full authorized Paperclip run and Opik/Hindsight/Wiki/skills evidence.

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
| Missing Coolify service/Worker, duplicate, fake approval, unreviewed promotion | `scripts/check-release-lanes.py --self-test` performs 13 fail-closed mutations | **Structural regression only** |
| Unauthorized feature-branch push bypass impossible at GitHub server | GitHub private-repo rulesets read returned HTTP 403 under current plan | **NOT VERIFIED / NOT ENFORCED** |
| Real failing production build preserves previous deployment | Deliberate destructive production failure not exercised | **NOT VERIFIED** |
| Real rollback of product or Hermes | Coolify previous image tags available; `current=null` in rollback-images response; no rollback executed | **NOT VERIFIED** |
| Source-overlay SHA ↔ running image digest for local MCPs | Upstream OCI revision labels are not overlay provenance | **OPEN / NO GO** |
| Hermes production end-to-end authenticated run | Coolify degraded and no safe cohort proof | **NO GO** |

A policy/schema check **cannot** prove GitHub server permissions, rollback, deployed image digest, canary success, authorization correctness or live source provenance. The CI job must never present such claims. `ops/release-lanes.json` is a dated inventory. Newly created resources require an authenticated Coolify/Cloudflare rescan and reviewed manifest update; the policy validator cannot discover them by itself.

Current GitHub private-repository rulesets API responded HTTP 403. Consequently CI + Paperclip approval provide process controls, **not unbypassable server-side branch protection**. Do not force-push `ci-approved`, manually overwrite approved image refs, silently redeploy unreviewed builds, or claim `DONE` for any service missing a live readback.

## Scope and owners

Keep all three existing Workers, secrets, production profiles and agent model allocations unchanged by this policy PR. No new Workers or global `main` rule. CHO owns reconciliation of existing KOMAA-1556/1559 and source PRs #28/#32/#36/#37/#39/#40, true native independent review decision, merge only after approval, post-merge CI and separately verified per-service deployments. This policy release is not authorization for a mass Hermes migration.

## Inventory freshness and concurrent releases

Snapshot 2026-11-04T17:02:30Z: **5 Coolify applications + 26 services = 31 distinct UUIDs**, plus 3 existing Cloudflare Workers. The extra Hermes Git release candidate was created at 16:49:56Z, after the previous 30-resource snapshot, and is represented explicitly. Another concurrent production change replaced the old upstream-only Paperclip Core runtime with a locally built overlay from PR #43; both source layers and runtime image ID are recorded separately. Fresh readback is required at merge time because other teams may create or redeploy services in parallel. A policy CI pass alone does not freeze live inventory or make a runtime release safe.

## Product promotion: local-CI attestation trust boundary

When GitHub-hosted Actions cannot start a job for an account billing block, the product promotion controller (`scripts/product_native_promotion.py`) refuses to treat that as a pass. It admits the release only with the root-owned local-CI attestation of the reviewed head, and only while that head's git tree equals the merged commit's tree.

That attestation is **release authority**, so its provenance is part of the gate, not an assumption:

- **Trust boundary**: the single writer is `product-local-ci-attest.service` (`User=root`) writing into `/var/lib/paperclip-gitops`, which is `root:root 0700`. No non-root principal can create, replace or edit a file in that tree.
- **What the consumer proves** before parsing any JSON: the directory is root-owned and not group/other-writable; the entry is opened with `O_NOFOLLOW` (a symlink is never followed) and must be a regular file; it must be owned `root:root`, single-link, not group/other-writable, and at most 8192 bytes. A FIFO cannot block the timer (`O_NONBLOCK`) and is rejected by the regular-file test.
- **TOCTOU**: ownership, mode, link count and size are read from the same descriptor that is then read for content (`fstat` + `read` on one fd), so replacing the path between check and read cannot substitute content.
- **What it still cannot prove**: atomic creation by the writer. The consumer reads one inode snapshot, so a concurrent replace yields either the old or the new file, never a mixture; the writer is expected to publish via temp file + `os.replace`, and a non-atomic write can only shorten the window, not forge a pass.
- **Required checks a privileged operator confirms** (agents cannot: the tree is root-only):

```bash
stat -c '%n %U:%G %a %h %F' /var/lib/paperclip-gitops/local-ci/*.json | head
stat -c '%n %U:%G %a %F' /var/lib/paperclip-gitops/local-ci /var/lib/paperclip-gitops
```

If any attestation is not `root root`, is group/other-writable, is not a regular single-link file, or the directory is writable by group/other, the controller denies with a named reason (`local_ci_attestation_owner_untrusted`, `local_ci_attestation_mode_untrusted`, `local_ci_attestation_link_untrusted`, `local_ci_attestation_dir_untrusted`, ...). The fix belongs to the root attester (chown/chmod + atomic publish), not to the consumer, and must not be worked around by relaxing the gate.
