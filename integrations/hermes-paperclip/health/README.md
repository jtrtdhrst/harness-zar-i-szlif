# Hermes Gateway production acceptance — observed checks, not health-only readiness

**Current result: PRE_CUTOVER_BLOCKED (9/15 gates passed as of 2026-11-03 UTC).** This folder is the single source for the host-side acceptance checker, distinct from the [offline evidence schema verifier](../verify_e2e.py). Never substitute one for the other.

| Source-controlled file | Approved VPS installation |
| --- | --- |
| [verify_production.py](verify_production.py) | `/opt/hermes-gateway-ops/verify_production.py` |
| [audit_runtime_skill_packages.py](audit_runtime_skill_packages.py) | `/opt/hermes-gateway-ops/audit_runtime_skill_packages.py` |
| [check-dualstack-gateway.sh](check-dualstack-gateway.sh) | `/opt/hermes-gateway-ops/check-dualstack-gateway.sh` |
| [readiness.sh](readiness.sh) | `/opt/hermes-paperclip-sync/check.sh` may invoke the verified acceptance wrapper; do not install duplicate timers |

Other inputs are the pinned role-skill synchronizer, immutable model map and toolset checks in [PR #9](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/9) under `roles/`, plus the Paperclip-generated runtime identity snapshot `/opt/hermes-gateway-ops/paperclip-agent-identities.json`. That generated snapshot contains live agent IDs and must be refreshed through Paperclip, not silently hand-edited in Git.

## Execution

Run the installed current verifier with the canonical generated runtime snapshot:

```sh
python3 /opt/hermes-gateway-ops/verify_production.py \
  > /opt/hermes-gateway-ops/last-production-acceptance.json
```

Exit `0` means every gate and a real Paperclip-issued Hermes run have been independently verified. Exit `2` means the cutover is blocked; other nonzero exits indicate a broken checker. As of 2026-11-03 this correctly returns **2**, rather than a false PASS. Do not edit the checker to force green status. The wrapper in `/opt/hermes-paperclip-sync/e2e-verify.sh` prints the exact failure set.

The dual-stack script uses unauthenticated *negative* requests to a Hermes route to prove Cloudflare Access permits only the existing VPS IPs and Hermes rejects invalid bearer credentials. It does **not** test the validity of the Paperclip Vault key.

## Empirical auth blocker

A real Paperclip run **KOMAA-1562 / `7f7df793-3ff0-4d17-b287-3126c34fcbff`** reached Hermes over HTTPS after Cloudflare IPv6 repair. It failed with `hermes_gateway_auth_failed`; Hermes origin log at 19:54:19 UTC confirmed rejection of the supplied invalid profile key for `POST /p/cho/v1/runs`. CHO was immediately returned to `opencode_local` and the test issue was terminalized `cancelled` with first-class evidence. A green public `/health` and unauthenticated HTTP 401 are not positive auth evidence.

The active CPO `local_external` Hindsight bank also lacks a successful exact-value new-session recall (the retain was queued but the independent recall returned unrelated old content). All other 13 Hermes profiles still use Cloud Hindsight. Production **cannot** be declared fully self-hosted or E2E-ready on the basis of CLI model/Wiki tests.

## Ownership and release

CHO owns independently approving the release. PR #28 owns these verifier sources and the strict offline receipt, PR #18 the adapter-only patch, PR #9 the scoped Wiki/role toolsets/schema-2 skill source, and PR #6 the Git-backed Coolify source rollout. No duplicate gateway code, no secret values committed, no bypassing Paperclip Core auth or reusing a shared Board token. Merge only after review, provenance and rollback readback.
