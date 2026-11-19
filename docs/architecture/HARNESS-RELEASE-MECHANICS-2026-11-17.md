# Harness / RepoWise current code mechanics — 2026-11-17

This is a **source-code snapshot**, not proof that a service is deployed or healthy.
Check GitHub's exact commit, the host's running image/digest, and the live
endpoints separately before asserting production readiness.

## Current Harness release admission (ZARI-240, merged in PR #112)

- `scripts/harness_release_admission.py`: fail-closed `evaluate` and
  `evaluate_build`; `ops/release-lanes.json` chooses eligible per-service
  resources. An absent `promotion_state` means **hold**.
- An explicit grant for the **specific Coolify UUID and source SHA**, an
  independent reviewer on the exact PR head, and a matching root-owned local
  CI attestation with a **verified HMAC** are distinct requirements.
- `scripts/harness_local_ci_attest.py` is the attestation producer/verifier.
  Admission also requires the immutable source SHA/image digest match; missing,
  stale, mismatched, revoked, expired or self-reviewed evidence denies release.
- `scripts/harness_delivery_controller.py` consumes admission before any
  build/promotion/deploy, verifies digest, health and deployed source SHA;
  unsuccessful deployment/readback attempts trigger rollback.
- The legacy Paperclip MCP auto-release implementation was removed from this
  repository. Do not use historical Paperclip release logic as the current
  Harness admission contract.
- `.github/workflows/release-lanes-policy.yml` covers GitHub CI policy; passing
  CI or merging a PR alone does **not** authorize production promotion.

## Ubuntu MCP code changes merged 2026-11-17

Code lives in `ubuntu-mcp/server.mjs` and tests in `ubuntu-mcp/test-auth.mjs`.
Today's commits introduced/refined the ChatGPT OAuth metadata/PKCE flow,
CIMD discovery, OpenAI callback-host compatibility, refresh-token and issuer
handling, the HTTP `405` contract for non-POST `/mcp`, legacy URL-key
compatibility, and `openssh-client` for SSH host-key inspection.
Source commits: `438a0f8`, `f308fc8`, `346bb8f`, `75f7086`,
`45f33e2`, `45fe9bf`, `3c8da46`. These are code facts, not live OAuth
E2E certification.

## RepoWise index and agent knowledge boundary

- The RepoWise workspace is split into `harness` and `product`; the
  host-side GitHub sync stages both `main` branches, indexes without network
  model calls, verifies the full git tier, and promotes after checking both
  Git SHAs and MCP smoke evidence. Sources: `ops/repowise/*`.
- The freshness job compares live checkout commits to the most recently
  fetched GitHub main, not merely index-to-local-checkout equality.
- Structured architecture/implementation facts belong in committed source
  and RepoWise. Multica issue/run/handoff state is the authority for
  execution; Hindsight is for verified experience, not replacement code facts.
- For any answer about "what works on production", read runtime evidence,
  exact deployment SHA and live checks. RepoWise alone cannot establish that.

Relevant merges: `6a572b3` (RepoWise sync/freshness), `b71bfc2`
(Harness release admission) and `3c8da46` (Ubuntu MCP latest merge at
this snapshot).
