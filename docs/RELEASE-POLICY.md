# Per-service release and production evidence policy

Owner: CHO (orchestration). Independent reviewers: CTO for release-critical infrastructure and the appropriate CPO/CTO for product changes. This is a governed release contract, not permission for ChatGPT or a runner to bypass the native Paperclip review lifecycle.

## Principle: release SHA, not branch name

The immutable artifact produced by a verified source commit is the unit of deployment. Each service has its own **integration ref**, **release ref or approved immutable image**, **environment**, and **readback**. No system-wide rule requires the production branch to be `main`.

**Product panel** keeps the already working chain: reviewed PR → `main` → Product CI `validate-product` → fast-forward-only `ci-approved` → Coolify webhook → exact production `/__release.json` SHA readback. Direct changes to `ci-approved`, force-push and manual overwrites of production refs are forbidden. Renaming the integration branch is a separate reviewed change to GitHub Actions, repository settings, and Coolify; do not do it for cosmetic consistency.

**Git-backed canaries** may use a purpose-specific candidate ref. They are not production even if the Coolify environment is named `production`, and they must not have automatic promotion to the production gateway.

**Local/upstream/pinned-image services** (Paperclip Core, Paperclip MCP, Hermes production, ComfyUI MCP) are not magically coupled to `main`. A GitHub merge is *not* deployment until an approved artifact is built and its immutable digest/source SHA is bound to the actual running Coolify image and verified through a service-specific authenticated/unauthenticated smoke. Never infer deploy provenance from Coolify's placeholder Git fields, a mutable image tag, or a healthy container. Convert these services to explicit Git-backed image pipelines only after a verified canary and native independent review.

## Gates based on risk, not bureaucracy

1. **Work candidate:** use issue-scoped branches. A PR is a proposal, not a release. Maintain its exact head SHA as the Paperclip work product, and repair stale SHA linkage rather than bypassing checks.
2. **Normal product/UI change:** passing tests, native independent issue review, and immutable-artifact promotion suffice. No additional user question or blanket manual approval if no human-only authorization is genuinely required.
3. **Security/access, agent runtime, MCP, secrets, data/schema or Hindsight/Opik changes:** independent CTO review plus CHO release decision, scoped canary, negative authorization tests, and rollback proof. Do not mass-switch Hermes agents before actual per-cohort E2E.
4. **Production acceptance:** prove source SHA → CI result → accepted PR/review → approved release ref or digest → Coolify deployed revision → live readback, with timestamp and rollback identifier. Healthy HTTP 200 alone is insufficient.
5. **Failure handling:** fail closed. The previous healthy release stays serving when build/tests/readback fail; never auto-merge an unreviewed PR, force-push a promotion ref, or re-deploy a known failing commit. A successful CI run does not cure a failed runtime deployment.
6. **Value delivery:** CHO regularly triages reviewed, valuable work stranded in open PRs; independently approve and release what passes, request rework for what fails, cancel duplicates with links to the surviving work. `DONE` requires production evidence, not a GitHub merge or an agent report.
7. **Scope isolation:** Cloudflare's three existing Workers remain in place. Do not create replacement Workers, new credentials or cross-project persistent volume access as part of release cleanup.

## Release-lane inventory and enforcement

`ops/release-lanes.json` declares the inspected initial lanes. The structural validator checks that every entry has a unique identity and a coherent release mode; it **does not** certify live deployment. Actual runtime status must be re-read before every release. New service lanes must be added only from inspected Coolify/source truth; unlisted services are **not** treated as verified.

Modes:
- `git_promoted`: source/CI → immutable release ref → automatic Coolify deploy → exact readback.
- `git_canary_manual`: dedicated candidate ref, isolated canary, no production auto promotion.
- `manual_pinned`: image/digest with explicit approved operator release and live attestation.
- `upstream_pinned`: externally versioned image, pin and validate runtime image/digest and application contract.

Currently, the product panel has a verified completed production E2E at commit `7322f946a5a395db29fa95d14da1ea9037e30d7c` (2026-11-04). The other lanes' observed baselines are **not** statements that their full release provenance is verified. In particular, Hermes production remains unready for mass agent cutover and the harness PRs still need native decisions.

## Constraints and security caveat

GitHub reported HTTP 403 for private-repository rulesets (account requires GitHub Pro or a public repository). Consequently, these repo-level checks **do not act as unbypassable server-side branch protection**. Do not assert the latter until GitHub rules/permissions are actually enforced and negative bypass tests pass. Native Paperclip reviewer admission and source-controlled CI are complementary controls, not substitutes for hard server-side protection.

Existing related delivery work must be reused: KOMAA-1556/1559 for both release lanes, KOMAA-1512/1496/1497/1513 for Hermes, and existing open harness PRs #28/#36/#37/#39/#40. CHO owns consolidation, independent reviews, implementation of the missing image/readback/automatic deployments, and evidence-based closure. This document changes no live branch, secret, service or agent.
