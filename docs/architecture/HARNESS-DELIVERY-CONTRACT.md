# Harness MCP delivery — authoritative operator & agent contract

Status: **source contract, not evidence of a successful production release**. Read alongside `ops/release-lanes.json`, `scripts/harness_native_delivery.py`, `scripts/harness_release_admission.py`, `scripts/harness_release_parity.py`, `ops/harness/INSTALL-RUNBOOK.md`, and the *live* Coolify/VPS configuration. For execution state consult native Multica issue ZARI-240, not this document.

## Ownership / one release path

- Repository: `miloszspyrka-code/harness-zar-i-szlif`, branch `main`; product `miloszspyrka-code/zar-i-szlif` has a **different** product release mechanism. An arbitrary feature branch is never a production source.
- Existing root-owned controller: `/usr/local/libexec/harness_native_delivery.py`, systemd oneshot `harness-image-delivery.service`, timer `harness-image-delivery.timer`; authoritative source `scripts/harness_native_delivery.py`. **Do not introduce a competing controller, extra watchdog or parallel deployment worker.**
- Service source/transport allowlist: `SERVICES` in the controller **AND** the reviewed `ops/release-lanes.json` entry. They are not interchangeable. A missing build context, missing Coolify UUID, unsupported resource, unknown runtime Dockerfile or `HOLD` must never become an automatic build.
- Operator (COO / designated release operator) owns the privileged VPS and Coolify write. CHO owns independent per-UUID release authorization for Harness MCPs; CTO reviews exact source and security independently; Harness Engineer prepares source and tests. Do not self-review or fake agent/grant/CI evidence.

## What actually runs

1. Verify current **remote** `refs/heads/main`, local clean checkout HEAD, installed controller blob SHA, active systemd unit/timer and effective source range. A stale checkout or range means `BLOCKED`, not `DONE`.
2. Determine the exact changed services and paths between the last verified delivery baseline (`HARNESS_BASE_SHA`) and the candidate SHA. **Never advance the baseline because a PR merged, a timer ran or a container is healthy.** Unclassified and manual/held changes stay pending.
3. For **each** changed service require: correctly mapped source folder/Dockerfile/Coolify UUID, merged reviewed PR, independent exact-head approval, accepted source SHA, an authorized release request, independently issued nonexpired revocable **per-UUID grant**, and signed local-CI HMAC attestation naming the immutable image digest. The gate in `scripts/harness_release_admission.py` is the authoritative admission decision. User requests alone do not override `HOLD`.
4. Only an admitted service may be built/pushed or promoted via the existing controller; Coolify target and image digest must match exactly. Read back the actual running image ID/digest, source revision, health and **authenticated positive and negative MCP E2E**; verify rollback source. If this fails, use the existing rollback path; no success claim.
5. Record exact Git SHA, digest, Coolify UUID, release request/grant/attestation evidence, production HTTP/tool calls and E2E outcome in the existing Multica issue. RepoWise describes source, not runtime truth.

## Current timer behavior / known limitation (2026-11-20)

The installed `--auto` resolves **both** `HARNESS_BASE_SHA` and `HARNESS_SOURCE_SHA` from the root-owned `/var/lib/harness-image-delivery/source-range.env`. **It does not fetch main or advance either SHA**. The host checkout must be advanced by an authorized mechanism before invocation. A newer GitHub main with stale source-range/checkout gives `source_parity:source_range_stale`. Thus `timer active` is not proof of end-to-end autodeploy. Any future improvement to discovery must still require exact remote/local SHA parity and per-service release admission before writes. Do not auto-advance the *delivered baseline* or relabel pending work as released.

The last observed Harness controller supports only the explicitly listed service transport routes, not every running Docker Compose service in Coolify. Manifest resources with `promotion_state=hold` or `auto_deploy_expected=false` are **not** evidence of configured autodeploy. Do not claim 13/13 routed Compose MCP deployments merely from configured image refs.

## Agent preflight (mandatory for CHO / CTO / COO / Harness Engineer)

Read this file **from current GitHub main**, then read exact code/manifest/runbook. For repository analysis query RepoWise workspace `harness` (not `product`) and verify `list_repos` `last_commit_at_index == current GitHub main SHA`. On stale/low-confidence RepoWise answers, open exact GitHub files; never infer gate policy from an unrelated Paperclip legacy approval script. Inspect current Multica issue/run, PR reviews, trusted main CI, root-owned gate/artifact status and Coolify UUID before any release assertion.

- Source PR / local tests / CI success: `SOURCE_READY`, **not production**.
- Unapproved SHA, `source_parity:source_range_stale`, missing request/grant/signature, held lane, ambiguous image or unauthorized actor: `BLOCKED`, **no deployment or invented grant**.
- Deployment claimed only after exact running digest/source readback, public authenticated and unauthenticated E2E plus rollback evidence: `PRODUCTION_VERIFIED`.
- `release_complete=false`, `pending_paths`, `held_outside_transport` or `request_unavailable` always mean the release range has remaining work; do not reset baseline or return global DONE.

## Read-only inspection commands

```sh
git -C /var/lib/harness-image-delivery/checkout rev-parse HEAD
git -C /var/lib/harness-image-delivery/checkout ls-remote origin refs/heads/main
systemctl is-enabled harness-image-delivery.timer
systemctl is-active harness-image-delivery.timer harness-image-delivery.service
grep '^HARNESS_.*_SHA=' /var/lib/harness-image-delivery/source-range.env
journalctl -u harness-image-delivery.service -n 12 --no-pager
```

For a **read-only** controller plan use the same `--mode plan --auto` and the same root-owned environment/manifest/gate paths as the installed systemd unit, without manufacturing authorization artifacts. Exit `0` from a plan or an idle/no-change tick does **not** mean an image was deployed.

## RepoWise indexing and freshness

RepoWise `harness` index is refreshed by the **existing** `repowise-github-sync.service` / timer and must be checked against the remote GitHub main SHA, not just its local staging checkout. The index may lag a newly merged commit. This document is the canonical retrieval anchor for queries `Harness controller`, `autodeploy`, `source-range`, `HOLD`, `CI attestation` and `production E2E`. Do not use archived `docs/knowledge/paperclip-archive/**/AGENTS.md` as the current Multica agent instruction source. Agent instructions must explicitly point at this file and the live prerequisites.
