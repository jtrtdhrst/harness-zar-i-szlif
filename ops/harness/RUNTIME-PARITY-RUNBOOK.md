# Harness runtime/source parity gate (ZARI-240)

## Failure this prevents

HARNESS_BASE_SHA == HARNESS_SOURCE_SHA used to make the 120-second
Harness delivery controller exit with no_change even when the host
checkout was stale and newer merged Plasmic MCP features were absent
from production. This is NOT evidence that release is complete.

## Source of truth and behavior

The read-only scripts/harness_release_parity.py probe checks:
1. Real origin refs/heads/main using authenticated git ls-remote;
   never rely on a cached origin/main or manually edited source-range.env.
2. Exact equality: upstream SHA == pinned HARNESS_SOURCE_SHA == local HEAD.
3. Exactly one running Docker container with the manifest Coolify UUID label.
4. Running revision from the OCI label or legacy SHA-prefixed image tag.
5. Valid revision commit and no git diff under plasmic-mcp/ between running
   revision and current main.

Every Harness AUTO cycle verifies real upstream main and the checkout.\nThe AUTO NO-CHANGE path verifies every manifest-managed service in the\nHarness delivery transport before reporting global success.
Unknown GitHub auth, missing revision/labels, ambiguous containers, stale
checkout, unapplied service changes and Git failures produce nonzero
denied/blocked. No git fetch, Docker mutation, auto-deploy, release grant,
timer creation or alternative controller is performed.

The standalone probe accepts --service NAME for other manifest services,
and the existing controller checks all manifest-managed transport services\nbefore global AUTO NO-CHANGE.

## Safe rollout (NOT achieved by merging this PR alone)

- PR #123 is the parent immutable-digest/controller security patch.
  This stacked PR must NOT be promoted to main before the parent is reviewed
  and merged, revalidated, and independently reviewed again at exact SHA.
- Root-host repo-scoped GitHub READ-ONLY credentials are a separate installation
  prerequisite. The current root checkout cannot authenticate a git ls-remote
  of this private repository. Do NOT print or borrow service credentials.
- The authorized operator installs the exact reviewed files through the
  existing Harness installation runbook and verifies installed hashes.
- Keep Plasmic MCP promotion_state: hold until independent SHA-bound review,
  attestation and per-UUID release permission are satisfied.
- Test the actual running image digest and authorized MCP initialize,
  tools/list, tools/call for Data Queries, including 401/403 and WAB readback.
  Source parity alone cannot close ZARI-229 or ZARI-240.

Read-only invocation:
python3 scripts/harness_release_parity.py --repo /var/lib/harness-image-delivery/checkout --service plasmic-mcp --expected-sha "$HARNESS_SOURCE_SHA"

Exit 0 means revision parity ONLY. Exit 2 means blocked with machine-readable
reason. Neither is a promotion authorization.
