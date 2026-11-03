# Paperclip MCP — automatic reviewed GitHub to Coolify release

This service is the deployment lane for the EXISTING Coolify Compose resource
gevr1m6rdj4t4fbhcjvqv8gg / paperclip-mcp. It does not modify Paperclip Core,
deploy Cloudflare Workers, change agent models or create Paperclip tasks.

## Trust boundary

- Polls ONLY main in miloszspyrka-code/harness-zar-i-szlif.
- Uses existing Paperclip Core Git credential helper for read-only source checkout.
- Before any deployment, Coolify's existing GitHub App checks that the exact
  40-character commit SHA is the merge commit of an actual merged GitHub PR
  whose base is main, that a separate reviewer approved the current PR head
  and that validate-paperclip-mcp completed successfully. Direct pushes,
  unapproved PRs, failed CI and unrelated repositories all fail closed.
- Only code paths in paperclip-mcp/mcp-gateway, src, plugin-runtime,
  plugin-skills, entrypoint.sh and Dockerfile can activate a deployment.
  Other monorepo components never trigger this service.
- A merged PR is NOT by itself independent CTO/CHO review. The deployed
  controller now refuses to release a watched change unless it can read
  a successful validate-paperclip-mcp GitHub Actions check on the PR head
  and an APPROVED GitHub review by a different GitHub identity, submitted
  against the current PR head commit. Outstanding CHANGES_REQUESTED denies
  release even if another review approved. Missing/invalid CI or review
  permissions fail closed. This does not replace Paperclip's first-class
  CHO/CTO execution review; both governance layers remain required.
- Configure GitHub branch rules separately for main: require a pull request,
  an independent approving review, a successful validate-paperclip-mcp check,
  no direct pushes and no force pushes. The existing App is intentionally
  not given Administration:write and cannot change this policy itself.
- No privileged GitHub credential or Coolify API token is copied into the
  release container, image, Git repository or logs. Existing signing key
  stays inside Coolify, rotated installation tokens stay in existing locations.

## Build and proof

- Clean clone of current main with recorded exact commit SHA.
- Build from paperclip-mcp/Dockerfile, using the same upstream Core image tag
  as production: ghcr.io/paperclipai/paperclip:2026.1023.0.
- Embed org.opencontainers.image.revision with the exact source SHA and keep
  an immutable local image tag paperclip-mcp:gitops-SHA.
- Run six focused native Git / authorization / MCP regression suites in the
  actual candidate image. Failed tests never reach production.
- Refuse race if main moved while preparing the image.
- Only the existing Coolify Compose image name paperclip-mcp:gitops-active
  is changed; existing networks, volumes, bootstrap and public URLs survive.
- Confirm new Docker image digest, exact SHA label, running healthy container,
  public /health HTTP 200 and anonymous MCP initialize HTTP 401.
- If deployment or validation fails, retag previous immutable Docker image and
  force-recreate service from the unchanged Coolify Compose resource.
- Record last_checked_sha, deployed_sha, image ID, PR ID and rollback image ID
  in /var/lib/paperclip-gitops/paperclip-mcp.json (root only).
- Host root systemd timer checks for source changes every two minutes.
- Coolify service is a Compose resource, not a Git-source Application. Deploys
  are performed by controlled docker compose on its existing Coolify project,
  and will not have a normal Coolify Git-source deployment UUID. They do have
  journald and immutable source/image readback evidence.

## Installation and operations

1. Install paperclip-mcp-auto-release.py to
   /usr/local/libexec/paperclip-mcp-auto-release.py (root 0700).
2. Install *.service and *.timer under /etc/systemd/system.
3. Build and test the current main SHA first; tag the verified image as
   paperclip-mcp:gitops-active.
4. Change ONLY the image field of the existing Coolify Service Compose to
   paperclip-mcp:gitops-active, keeping the GitHub App bootstrap and all mounts.
5. Run python3 /usr/local/libexec/paperclip-mcp-auto-release.py --plan.
6. Run python3 /usr/local/libexec/paperclip-mcp-auto-release.py and verify
   source SHA, container label, health, auth and public MCP smoke.
7. Enable and start paperclip-mcp-auto-release.timer after successful initial
   deployment. A harmless code comment canary in a merged PR then proves
   automatic polling-to-production; verify Docker digest and SHA changed.
8. Inspect systemctl status/journalctl for release failures. The service never
   prints tokens. If a main commit does not belong to an actual merged PR,
   it will be refused until corrected.
9. For rollback: stop the timer, restore previous tagged image using the
   state previous_image_id and recreate ONLY paperclip-mcp. Do not modify
   credentials or unrelated Coolify services.

## Important limitation

This controller is intentionally scoped to paperclip-mcp. Other harness
services (ComfyUI, Plasmic, Opik, etc.) require their own independently
tested manifests, build contracts, health criteria and rollback before being
admitted. An all-services wildcard restart would risk production.
