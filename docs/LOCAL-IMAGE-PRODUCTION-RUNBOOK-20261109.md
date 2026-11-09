# Local image production and GitHub runner — verified operations (2026-11-09)

This file records observed **production** state, recovery procedures and remaining permissions. It does not claim automatic E2E releases are ready.

## Actual production routing

- Public: `https://panel.zariszlif.pl` (Coolify Caddy managed on Ubuntu).
- Caddy active config: `/data/caddy/Caddyfile`, **production** `panel.zariszlif.pl` route.
- Primary upstream: `zis-image-release:80` (Coolify image-only application `cs847jiwtuq5rlm8ntjeohgf`).
- Fallback upstream: `zar-i-szlif-web:80` (legacy Coolify Dockerfile application `k0vwdsjazxguvgmh4qixjgxn`, auto-deploy disabled).
- Native Caddy `lb_policy first` with `health_uri /healthz`, `health_body ok`, two-second interval and limited failover retries.
- Exact recovery backup: `/data/caddy/Caddyfile.pre-prod-image-switch-20261109`. Do not remove the legacy fallback until replacement rollback has been proven and explicitly accepted.
- Same release on primary and fallback: `98cd058155dbf4c268777246fc510324f98f7dc5`; public `/__release.json` and `/healthz` verified.

Loopback registry is a separate Coolify Docker Image app `g0xdkztpmjnhgwms7qelzxqd` with a persistent volume. Registry URL `http://127.0.0.1:5000/v2/`, no public FQDN. Its image is `127.0.0.1:5000/zar-i-szlif-web:98cd058155dbf4c268777246fc510324f98f7dc5`, immutable manifest digest `sha256:478ab8d0fd10fbbb4f6162e05f41ae4d82f3e75745be10cacf48d6833847fdfe`. The image was built on this VPS and deployed from the registry by Coolify (not rebuilt by Coolify).

## Failure-injection evidence

- Previously passed: stop the image-only container, verify Caddy switches public traffic to the legacy upstream and returns to primary after recovery.
- New controlled failed image deploy: `rna32sshgvxv8auocyignkhs`. The image refused startup when `SOURCE_COMMIT` was invalid. Coolify reported deployment failure and rollback; independent public HTTP polling showed **24/24 successful** `/healthz` + `/__release.json` readbacks, all at the approved SHA.
- Restored exact `SOURCE_COMMIT`; successful Coolify deployment `9eaa4c84gcrjixbjuuarhcpu`. The image-only app's own auto-deploy is disabled; the public proxy does not depend on GitHub webhooks.

Safe public readback:

```bash
curl -fsS https://panel.zariszlif.pl/healthz
curl -fsS https://panel.zariszlif.pl/__release.json
curl -sSI -H 'Accept: application/vnd.oci.image.index.v1+json' \
  http://127.0.0.1:5000/v2/zar-i-szlif-web/manifests/98cd058155dbf4c268777246fc510324f98f7dc5
```

Emergency reversion to the original production upstream: validate the saved Caddyfile independently, then restore that backup to `/data/caddy/Caddyfile`, validate again with `docker exec coolify-caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`, and reload with `docker kill --signal=SIGUSR1 coolify-caddy`. Always verify public HTTP endpoints after switching.

## Native product release gate

- Harness PR #82 introduced exact merged-PR provenance for squash and a non-runtime documentation-only no-op for Product PR #164. It still requires passing GitHub CI and native Paperclip approval for runtime changes.
- Harness PR #83 fail-closes future runtime branch advancement until a registered runner and a fully verified local-image release pipeline are present.
- Deployed version of `/usr/local/libexec/product_native_promotion.py` passed **22/22** tests. `product-native-promotion.service` returns success for the current docs-only `main` advancement, with `ci-approved` unchanged and public release healthy.
- Absence of `/var/lib/paperclip-gitops/zis-image-promotion-ready.json` is **intentional**. Never fabricate a readiness marker to unblock deployment.
- `main`: `81c4b068b89f4c035098c6c9107f755f56919a87`. `ci-approved`: `98cd058155dbf4c268777246fc510324f98f7dc5`.

## Product repository self-hosted runner

Official GitHub Actions runner **2.338.2** is unpacked at `/opt/zis-actions-runner`; release archive SHA-256 `baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40` was verified before extraction. Dedicated local account `actions-zis` and systemd unit `zis-github-runner.service` are prepared.

**Not registered.** Existing GitHub App `5398752` has `administration:read`. GitHub rejected the repository registration-token POST with HTTP **403**, because repository runner registration requires `Administration:write`. Never attempt to bypass this restriction. This is the only remaining manual credential authorization for runner registration.

A root-owned one-shot bootstrap exists:

```bash
sudo /usr/bin/python3 /usr/local/libexec/zis-register-product-runner.py
```

It automatically requests an ephemeral registration token *only if* the existing App has been explicitly granted `Administration:write`. As a **less privileged alternative**, an authorized administrator may use GitHub's own UI (**Product repo → Settings → Actions → Runners → New self-hosted runner**) to obtain an expiring one-time registration token. Place it directly on the VPS without putting it in a chat, e.g. using an interactive SSH session:

```bash
sudo bash -c 'umask 077; read -rs -p "GitHub runner registration token: " t; echo; printf %s "$t" > /root/coolify-secrets/zis_runner_registration_token; unset t'
sudo /usr/bin/python3 /usr/local/libexec/zis-register-product-runner.py
```

The bootstrap verifies root-only permissions, registers repository runner `zis-local-build` with labels `local-build,zis`, deletes the one-time file after successful registration, and enables/starts the systemd service. It never prints the registration token. Do not run untrusted PR code with a runner attached to the production host's Docker socket. Scope build workflows to reviewed `ci-approved` commits.

**Registration is not delivery readiness.** The image-build workflow and image promotion controller must still be connected, and tested with a reviewed release SHA, immutable registry digest, Coolify image-only deploy, exact public HTTP readback, failure injection and recovery, before any readiness marker is authorized. Harness non-MCP source directories remain in Git for agent context but must not gain automatic image-build triggers.
