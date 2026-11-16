# Source-only folders and production image builds

Policy (2026-11-09): retain non-MCP sources in this repository for agent and RepoWise context. Source presence does **not** authorize a Docker build, deployment, or Cloudify/Coolify service creation.

## Two distinct operations

1. **Validation**: lint and unit tests may run on scoped source changes; no Docker image build for source-only folders.
2. **Promotion**: for an actively deployed application, build an immutable image **on the self-hosted build runner** after the reviewed source SHA passes CI. Push the immutable image to a registry, then configure Coolify to pull **that exact digest**. Production must not git-clone and build source independently. Confirm running digest, health, endpoint and rollback before success.

Until a registered, online self-hosted runner and registry publication are verified, **do not** change the live production application's source mode to an image mode: that would interrupt existing releases. No claim that the runner or image release is currently operational.

## Classification

Source-only (no automatic image builds solely because they are in Git): `comfy/`, `plasmic/`, `qdrant/`, `supabase/`, `mautic/`, `opik/`, `paperclip/`, `cloudflare-ingress/`, `shared-ingress/`, `_archive/`, `kod-aplikacji/`, `kod-mcp/`, `docs/`.

Standalone MCP sources (`*-mcp/`) are independently eligible for narrowly scoped CI builds **only after** deployed-resource source binding and release policy verification. `integrations/hermes-paperclip/gateway/`, `integrations/*-overlay/`, `opik-run-enricher/` and `mcp-edge/` are explicit non-MCP or infrastructure exceptions: build only for a specifically approved active runtime, not on every repository push. Never classify by string matching alone when a manifest declares a special case.

For Coolify Git-backed source references used only for RepoWise bootstrap, disable automatic deployment; they are not application release targets. Do not delete them or their source code during repository cleanup.

## Production acceptance criteria

Reviewed commit SHA -> runner-built image digest -> immutable registry artifact -> image-only Coolify deployment -> verified runtime image digest, health/readback, rollback image retained. An image built directly by Coolify from Git **fails** this new local-build-only target even if it serves traffic.

No unrelated source-only path change may trigger an image build, nor can an MCP-only change rebuild non-MCP sources. Tests may still run without building images.

## Observed local-image canary (2026-11-09)

- Production `zar-i-szlif-web` (Coolify UUID `k0vwdsjazxguvgmh4qixjgxn`) still uses Dockerfile source mode. Git webhook auto-deploy was switched **off**; existing production remains on `98cd058155dbf4c268777246fc510324f98f7dc5`.
- Local Docker build of the approved commit from the Product RepoWise mirror completed; Dockerfile tests and runtime build passed.
- Private registry: Coolify project `local-build-image-registry`, Docker Image app `g0xdkztpmjnhgwms7qelzxqd`, persistent registry volume, listening **only** at `127.0.0.1:5000`. No public FQDN. Repository `127.0.0.1:5000/zar-i-szlif-web`.
- Immutable OCI manifest digest of the tested version: `sha256:478ab8d0fd10fbbb4f6162e05f41ae4d82f3e75745be10cacf48d6833847fdfe`. SHA-specific tag `98cd058155dbf4c268777246fc510324f98f7dc5`. Registry HEAD request returned matching digest.
- Image-only Coolify canary: project `zis-prebuilt-web-canary`, app `cs847jiwtuq5rlm8ntjeohgf`, no public FQDN. Successful deploy `jhhdy5nprjhpxrt5lzkxmbew` verified exact runtime release SHA and HTTP /healthz.
- **Failure injection:** setting the canary's runtime `SOURCE_COMMIT` to an invalid value caused the expected startup refusal and failed deploy `rbdqadkkkfl7fd1yrnbhjcum`. Coolify reported rollback, but the preserved container briefly returned **connection refused** despite a `healthy` health status. Therefore Docker's nominal health state is NOT sufficient rollback proof. After restoring the valid SHA, deploy `jpdf2phu5xc3hk0aocrlei1r` and HTTP readback passed.
- GHCR push was attempted and refused with `permission_denied`; the private loopback registry works instead.
- The installed Coolify GitHub App reports repository permission `administration:read` and **not** `administration:write`; GitHub requires Administration (write) to register repository self-hosted runners. Neither Product nor Harness repository has an online runner. No GitHub Actions runner E2E or automated production cutover is claimed.
- The native product promotion timer currently denies new main promotions with `non_merge_commit_on_main`. That issue is separate from image build delivery and must not be bypassed by promoting unreviewed commits.
- A disabled, nonpublic `image-mode-conversion-probe` application remains in Coolify pending manual deletion; native Coolify API rejected in-place change from Git-backed Dockerfile app to Docker Image mode. Production changeover therefore requires a staged image-app cutover, not an untested in-place build_pack mutation.

**Acceptance:** before cutover, require a registered runner or approved equivalent local scheduler, reviewed source and exact SHA, successful build and immutable image publication, an image-only production route with synchronized `SOURCE_COMMIT`, HTTP readback, and demonstrated rollback with real HTTP availability. Test-workspace success alone is not a production release.

## Harness MCP release admission (ZARI-240, source only)

The Harness delivery controller must not treat a merged pull request as permission to build or deploy. Two repository-owned modules define the fail-closed contract; the privileged controller is expected to call them, and both are **not installed** on any host by this repository change.

1. `scripts/harness_release_admission.py` — `evaluate(manifest, request, grant, attestation, now)` returns an admission record or raises `Denied` with a stable audit reason. It denies when any of the following is true:
   - the service is unknown, ambiguous, not harness-owned, or its Coolify UUID/kind differs from `ops/release-lanes.json`;
   - the resource is on `hold` (a missing `promotion_state` counts as hold) and no per-UUID grant exists;
   - there is no revocable, unexpired, audited per-UUID grant bound to that exact Coolify UUID and source SHA — a manifest edit is never a substitute;
   - the independent reviewer equals the producer, holds the wrong reviewer role for the lane, or approved a different PR head than the one being released;
   - the source SHA is not the merged main squash SHA, or the base ref is not `main`;
   - the root-owned local-CI attestation is missing, unsigned, not produced as uid 0, **produced by a root-executed test run**, missing a policy digest, stale, failing, empty, or covers paths outside the service root;
   - the immutable image digest is absent or differs from the attested digest.

   Hold is evaluated before any artifact, so satisfying later evidence checks can never promote a held lane. The module is read-only and exposes no force/skip/override switch.

2. `scripts/harness_local_ci_attest.py` — root-invoked attester with **no caller-supplied execution surface and no alternate policy path**: it accepts only `--service`, `--source-sha`, `--base-sha`, `--image-digest`, `--dry-run`. Commands, repository root, output directory, key file and runner uid/gid all come from the root-owned policy `/etc/paperclip-gitops/harness-ci-policy.json` (`0600`, non-symlink, absolute paths). Tests run as the policy's unprivileged `run_as_uid`/`run_as_gid` with `PR_SET_NO_NEW_PRIVS`, an empty supplementary group set, a fresh session and a sanitized environment (no inherited credential, token or proxy variable); **uid 0 execution is refused and never attestable**. The checkout must sit at exactly the requested source SHA with a clean worktree, and policy/key files are opened `O_NOFOLLOW` with `fstat` on the descriptor, closing the symlink-swap/TOCTOU window. The attestation records the policy digest and runner uid, is HMAC-signed, written `0600` under `/var/lib/paperclip-gitops/harness-attestations/<service>-<sha>.json` with an exclusive lock and idempotent reuse. No network credential, no GitHub Actions billing dependency.

**Not claimed here:** nothing is deployed or installed by this change, and namespace-level network isolation for the test run is *not* implemented by these modules. The remaining owner/controller steps are (a) install the two modules, the policy file and the attestation key on the approved host, and (b) change the existing root controller `harness_image_delivery.py` to call `harness_release_admission.evaluate` before any promotion and to abort on `Denied`. Network isolation of the test runner and the exact policy contents are part of that audited host activation, not of this source change. Until (b) is installed and read back, the controller behaviour is unchanged and no hold is enforced at runtime.

**Known same-defect sibling path (not owned by ZARI-240):** `paperclip-mcp/gitops/paperclip-mcp-auto-release.py` verifies merged PR, CI and native review but never consults `ops/release-lanes.json`, so it can auto-release `paperclip-mcp` while the manifest holds it. That path belongs to the `paperclip-mcp` owner and needs its own bounded change and review.

