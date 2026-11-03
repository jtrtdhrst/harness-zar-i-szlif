# Per-agent Paperclip runtime skills — 45 pinned assignments

The production skill inventory is **120 desired agent/skill assignments**, separated by origin rather than copied blindly:

| Origin | Assignments | Pinned packages | Owner |
| --- | ---: | ---: | --- |
| Approved company-managed | 75 | 27 | `sync_profile_skills.py` + schema-2 `profile-skill-allowlist.json` |
| Paperclip bundled/core and role-local | 45 | 6 | `sync_runtime_skills.py` + `runtime-skill-allowlist.json` |

The 45 non-company assignments are three upstream Paperclip skills (`paperclip`, `complain`, `suggestion-box`) for all 14 roles, plus exactly one specialised package each for COO (`status-card-query`), Harness Engineer (`paperclip-opencode-health`), and Email Creative (`kompas-brand-email`). No other profile receives those specialised packages.

This is **one existing systemd timer** `hermes-profile-skills-sync.timer`, not parallel timers or a second runtime policy. Its `Type=oneshot` service calls the two independent, SHA-pinned installers in sequence. Both are idempotent and fail closed on source drift, unpinned content, unsafe symlinks or unauthorized assignments. Bundles are written only to the role's own `skills/company-managed/` and `skills/paperclip-managed/` directories; the source Paperclip files are never modified.

## Safety and source

The non-company installer reads six exact approved source directories **from the running Paperclip container**, using `docker cp` to a short-lived private temporary directory. A full SHA-256 manifest approves every file including references and scripts (19 unique files, 227 file/role copies). No Docker socket, bearer token or credential is passed into the model. Source path traversal and symlinks are denied. Files are copied atomically, mounted read-only for Hermes UID 10000. Extra unassigned destination files cause fail-closed rather than silent ingestion.

Pinned source: observed Paperclip `ghcr.io/paperclipai/paperclip:2026.1023.0` and the live 2026-11-03 Paperclip desired skill assignments. If the Paperclip image or desired assignments change, a new review must approve the updated pins; do not force green checks by weakening the manifest. The tool is **NOT** a replacement for the runtimeMcp permission bridge.

## Reproducible verification

On a host with the original runtimes and paperclip role snapshot:

```sh
python3 /opt/hermes-gateway-ops/sync_profile_skills.py
python3 /opt/hermes-gateway-ops/sync_runtime_skills.py
# Expect exit 2 if any approved files are missing/drifted.
python3 -m unittest discover -s /opt/hermes-gateway-ops/tests -v
```

Following approved release, to install:

```sh
python3 /opt/hermes-gateway-ops/sync_profile_skills.py --apply
python3 /opt/hermes-gateway-ops/sync_runtime_skills.py --apply
python3 /opt/hermes-gateway-ops/audit_runtime_skill_packages.py
python3 /opt/hermes-gateway-ops/verify_production.py
```

A green 120/120 file audit proves only **assigned skill-file availability and SHA parity**, not that the Paperclip-run adapter has already loaded those skills or that any privileged MCP tool call works. Those require a real authenticated Paperclip-issued Hermes run, Opik trace and correct ephemeral grant. `verify_production.py` must continue to report `PRE_CUTOVER_BLOCKED` until every unrelated E2E gate passes.

## Rollback

Preserve the installed approved source SHA, original systemd service unit, the profile folder snapshot and read-only audit report before applying. Restore the previous `hermes-profile-skills-sync.service` unit, `systemctl daemon-reload`, and the relevant role skill directories from the pre-deploy backup; leave the canonical Paperclip skill library and all agent models untouched. Disable no other timers. Document SHA, restore receipt and live readback in Paperclip before any CHO release approval.
