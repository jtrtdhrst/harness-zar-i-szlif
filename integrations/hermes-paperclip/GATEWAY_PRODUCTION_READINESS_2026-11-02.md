# Migration staging readback — 2026-11-04 (current; supersedes dated historical observations below)

**Decision: STAGING READY / AGENT CUTOVER NO-GO.** All 14 Paperclip agents keep their current `opencode_local` adapters and models. This is a real Coolify candidate with a verified container, not a claim that the cross-service issue-run protocol has passed.

## Verified source and independent runtime

| Proof | Readback |
| --- | --- |
| Harness feature candidate | [PR #36](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/36), exact SHA `8f2bd8674b0c730c4443aaa395b72b7982a6d8fb` |
| GitHub CI for PR #36 | `validate-hermes-gateway-image` and `validate-paperclip-mcp` both success; no release implied |
| Coolify GitHub-backed shadow app | `yh20mb2rurecnmn60t5vfc3s`, repository `harness-zar-i-szlif`, branch `KOMAA-1512-receiver-20261104`, base `/integrations/hermes-paperclip/gateway`, Dockerfile `/Dockerfile` |
| Shadow deployment | `pid1srcg0ekxxgsu4jw3nlki`, `finished`; immutable Docker image `sha256:3be829d276d3039f9fd0625fa4c8a632b96df338ef5e9c8c513fb0880c8d3528`; Docker `running/healthy` |
| Production app (preserved) | `2sganhxhhnioiqh4an9g2f4k`, image `sha256:813992ff23d9b82936ad5f35ed9f1d74908584d44888197b492c4615680cd65a`, Docker healthy; public `https://hermes-poc.zariszlif.pl/health` returns HTTP 200 |
| Source-model limitation | Production app still uses an **inline Dockerfile**, `source_type=null` and repository metadata `coollabsio/coolify`, not the harness source. Coolify connector refused source/inline Dockerfile conversion; do not pretend this is Git-backed |
| Isolation | Shadow has no public domain, no production `/opt/data` mount and auto-deploy OFF. It uses only an explicitly synthetic API key; no private service key was transferred |
| Memory metadata | Vectorize administrative inventory has exactly 14 expected `hermes-*` banks; this does not prove authenticated profile/bank denial or model-run recall |

Live **non-inference** HTTP probes on the Git-backed shadow app:

- Root `POST /v1/runs`: missing bearer **401**, invalid bearer **401**, correct synthetic bearer with malformed JSON **400**, null/invalid `paperclip_run_mcp` envelope **403**.
- A newly created **synthetic** `designer` profile in the shadow has its *own* file-mode-0600 key: correct profile bearer with malformed JSON **400**; global/default bearer **401**; wrong bearer **401**; malformed MCP grant **403**.
- No model inference, real Paperclip issue credentials, role tools/call, secret synchronization or Opik production correlation was initiated by these negative tests. Do not infer that scope revocation, grant authenticity or session cleanup passed from 401/403 alone.

## Blocking prerequisites for 14-agent migration (keep fail-closed)

1. **Native profile secret binding.** Paperclip's secret catalog lists two historical Hermes keys with usage targeting a *retired Hermes Test* and another old identity; there is no positive evidence of a correct `API_SERVER_KEY` secret binding for each of the 14 current agents. The previous real CHO Hermes run failed with profile-specific HTTP 401. Provision/bind each role's key using authorized Paperclip secret provider/Vault workflow, and prove correct named-profile 400 (malformed JSON) and wrong-profile 401; do not transfer keys through issue text, chat, git, logs or unmanaged VPS/DB copies.
2. **Per-run MCP authority.** Source-controlled PR #36 now contains patched Hermes admission/cleanup and candidate adapter diff; independent CTO/CHO security review remains required. Demonstrate a **real** Paperclip-issued run ID, real run/agent/issue-scoped grant, Wiki and versioned skill tool calls, and denied wrong agent/run, expired/revoked token, and after-run reuse. A synthetically accepted API request is insufficient.
3. **Hindsight and Opik.** On that same real Paperclip-issued run, prove profile's own Hindsight retain, independent-session exact recall, cross-bank denial, and Hermes-native Opik trace including the exact Paperclip run UUID plus tool/model/usage spans. `14/14` bank metadata alone is insufficient.
4. **Source-controlled deployment and rollback.** After reviewed merge, rebuild the immutable image from approved `main`, not from this feature branch. Existing production app cannot be converted to Git-backed source through the supported Coolify update call. Use the **existing** Git-backed successor, preserve the current production image and 3.2 GB `/opt/data` volume, perform an approved stopped-writer backup/restore into a separate target volume only at the release window, then transfer the legacy `hermes-gateway-poc-v2` network alias / Cloudflare origin with exact URL and Docker SHA readback. Never copy live mutable state while two gateways are running; do not create a new Worker. Roll back aliases and the verified old container on any failed gate.
5. **Independent acceptance.** CTO reviews source/security; CHO owns review/merge/DAG/release. `KOMAA-1564` is the native adapter/receiver subtask, `KOMAA-1512` the authoritative parent, `KOMAA-1496` real agent E2E, `KOMAA-1497` release. [PR #28](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/28) is the canonical **strict offline structure** gate and intentionally cannot assert a live PASS without authenticated source readbacks. No self-approval or `status=done` override.

## Rollout order and exact stop conditions

- **Wave 0:** Designer (DeepSeek) alone; retain original `adapterType`, `adapterConfig`, model, tool grants and runtime revision ID as rollback.
- **Wave 1:** COO and UI QA only after the Designer run has full first-class PASS and no memory or access leakage.
- **Wave 2:** CEO, CMO, Mascot Designer, Lifecycle Ops.
- **Wave 3:** Engineer, MCP Engineer, Email Creative, CPO, Harness Engineer, CTO, CHO.
- On each wave: exact issue UUID/run UUID, `/p/<profile>/v1/runs` profile-key proof, Named MCP Wiki/skills scope and negative tests, exact Hindsight recall, Opik trace correlation, image SHA/digest, review approval, and agent adapter config readback. Stop at **first failed** condition. Restore only the affected cohort's previous adapter config via native Paperclip revision rollback; never flip 14 simultaneously.

**Warning about local host verifier:** `/opt/hermes-gateway-ops/verify_production.py` describes itself as read-only but invokes `sync_profile_skills.py`, `reconcile_model_map.py` and `apply_gateway_api_toolsets.py`. Those may change configuration. Do not use it as a read-only preflight until those calls are separated into explicit opt-in `--apply` operations. Use the source-controlled `verify_e2e.py` (PR #28 version) for *offline structural* evidence checks and live connector evidence for runtime acceptance.

---

> **Production update — 2026-11-03:** This document records the 2026-11-02 Gateway baseline. The current approved company-skill synchronizer has been upgraded to **schema 2**: 14 profiles, 75 company skill assignments, 27 unique SHA-256 pinned skill bundles, including all reference/scripts/assets. It is the same version deployed in `/opt/hermes-gateway-ops/sync_profile_skills.py` on VPS. The old figures “68 assignments / 20 pins / 4 tests” below are **historical only**. The new production schema-2 unit suite passed **12/12** including per-role isolation, idempotence, source+asset hash enforcement, symlink denial and destination drift repair. See `.github/workflows/hermes-skill-bundles.yml` for GitHub Actions regression; no automated deploy.
>
> **Cutover remains blocked:** the dedicated native Paperclip issue run has not yet passed authenticated `hermes_gateway` → run-scoped Paperclip MCP → independent Hindsight exact recall (especially CPO local_external) → same-run Opik. That gate is owned by canonical [PR #28](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/28); adapter candidate belongs to [PR #18](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/18). Do not merge as E2E acceptance.

# Hermes Gateway — isolated profile operations and pre-cutover readiness

**Validated:** 2026-11-02 UTC  
**Repository:** `miloszspyrka-code/harness-zar-i-szlif`  
**Coolify application UUID:** `2sganhxhhnioiqh4an9g2f4k`  
**Gateway API:** `https://hermes-poc.zariszlif.pl` (authenticated)  
**Scope:** Gateway and isolated Hermes profiles. **Explicitly excludes switching Paperclip adapters (0/14), DeepSeek V4.1 provider onboarding, and full Paperclip task-delivery acceptance.**

## Decision

**Gateway limited pre-cutover acceptance: PASS for isolated, read-oriented profile operation and native memory tests.**  
**Unattended production agent execution: NO-GO until sandbox, per-run Paperclip MCP auth, and full Paperclip E2E are independently accepted.**

A healthy HTTP endpoint, a loaded skill, or a successful CLI memory call does **not** establish Paperclip production readiness.

## Ownership and deployment

- Paperclip owns assignments, branch/DAG lifecycle, reviewers, approval, and production delivery decisions.
- Hermes Gateway is the agent runtime, with one profile directory and one Hindsight bank per future Paperclip agent.
- Vectorize.ai **Hindsight** is the native memory provider. Do **not** confuse it with Cloudflare Vectorize.
- Opik traces model calls, tool calls, and token usage.
- Canonical instructions and company skills originate in **Paperclip**. Approved Wiki is mirrored read-only; user-facing product work uses the product repo, infrastructure work uses the harness repo.
- No modifications to Paperclip Core, its scheduler, agent adapters, models, three existing production Workers, or disabled agent watchdogs/routines/heartbeats were made as part of this Gateway remediation.

### Profile layout

Persistent Docker volume:

```text
/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data/
  profiles/<profile>/
    .env                               # private, never print or commit
    config.yaml                        # named model, API tool policy, Wiki MCP
    hindsight/config.json              # bank_id = hermes-<profile>
    skills/company-managed/<name>/SKILL.md
  mcp/wiki_scoped.py                   # read-only profile-scoped server
  wiki-paperclip-test/wiki/            # 1-minute canonical Markdown mirror
```

The 14 active profiles are: `ceo`, `cho`, `cmo`, `coo`, `cpo`, `cto`, `designer`, `email-creative`, `engineer`, `harness-engineer`, `lifecycle-ops`, `mascot-designer`, `mcp-engineer`, `ui-qa`. Distinct `API_SERVER_KEY` values existed before this change; they were neither copied nor rotated. Profiles `hermes-test` and `delivery-release-manager` are retained for historical audit only; their API toolsets are disabled to `clarify` and the Hermes Test MCP assignments are disabled. The root/default profile also exposes only `clarify` on its API surface.

## Security boundaries

**Active API toolsets are explicit role allowlists**, versioned at `roles/gateway-api-toolsets.json`. Every active profile has `memory`, `skills`, and `wiki_fs`. Visual roles may have `image_gen` / `vision`; CHO and engineering/orchestration profiles do not automatically inherit visual tools. These builtin toolsets are **not** a substitute for native Paperclip role-granted MCP tools.

On all 14 active profiles, API exposure of these execution surfaces is disabled:
`hermes-cli`, `terminal`, `file`, `code_execution`, `computer_use`, `cronjob`, `delegation`, `browser`, `session_search`, `connections`.

The underlying Hermes container **still runs with root UID, local terminal backend, a writable root filesystem, and no verified cap-drop**. Toolset deny is defense-in-depth, **not** a container sandbox. Do not re-enable terminal/CLI/file/code tools for untrusted, network-triggered agent work until an independently verified restricted execution backend exists.

Anonymous GET requests to `/p/{cho,cpo,engineer,mascot-designer,ceo,hermes-test}/v1/models` returned HTTP **401** on 2026-11-02. A negative anonymous test does **not** establish that wrong-profile keys cannot be used across profiles; re-test distinct authorized key isolation through a supported secret-aware test path before agent cutover.

### Read-only Wiki MCP authorization

`wiki/wiki_scoped.py` is deployed as `/opt/data/mcp/wiki_scoped.py`. Each active profile config must set:

```yaml
mcp_servers:
  wiki_fs:
    command: /opt/hermes/.venv/bin/python
    args: [/opt/data/mcp/wiki_scoped.py, --profile, cho]  # use actual profile
    enabled: true
    tools:
      resources: false
      prompts: false
      include: [wiki_list, wiki_read, wiki_search]
platform_toolsets:
  api_server: [clarify, memory, skills, todo, web, wiki_fs] # example, role-specific
```

Permitted Wiki scope: `wiki/concepts/**`, `wiki/sources/**`, and `wiki/agents/<own-profile>/**`; harness governance pages under `wiki/agents/harness/**` are additionally accessible to CHO and Harness Engineer. `wiki/context-archives/**`, other roles' instructions, absolute/traversal paths and symlinks are rejected. A shared document directory is still a trust boundary: review the common pages before adding sensitive content.

The Wiki mirror is updated by the *existing* `hermes-test-wiki-sync.timer` every minute. Although its historical name says "Test", it is now shared by active profiles. Its `rsync -rt` preserves original file modification times. Assess freshness using `systemctl status hermes-test-wiki-sync.service` and **checksum comparison**, not the Markdown file's mtime.

Known boundary: native Paperclip Wiki plugin on the Named MCP Gateway still requires a trusted Paperclip **run-scoped token**; `wiki_fs` is a *read-only, on-host mirror alternative*, not a fix for that plugin. `KOMAA-1512` remains the owning bridge issue.

## Skill governance and synchronization

- Explicit per-agent allowed company skills: `roles/profile-skill-allowlist.json`.
- **68 role-to-skill assignments; 20 unique skills**, each pinned to an approved SHA-256 of its `SKILL.md`.
- `roles/sync_profile_skills.py` audits by default; `--apply` copies changed allowed `SKILL.md` atomically, preserves SHA, and never installs unlisted skills.
- Any modified Paperclip source whose hash is not approved in the manifest returns **`UNAPPROVED_SOURCE_SHA`**, failing closed. A new approved skill revision requires independent review and a separately reviewed manifest update.
- Only firm-specific `company-managed` skills are governed by this allowlist. Hermes' bundled builtin skills are separate and may still appear in the built-in catalog.
- Active systemd unit: `hermes-profile-skills-sync.service`, triggered every two minutes by `hermes-profile-skills-sync.timer`. Its `ProtectSystem=strict` sandbox only allows writes under the Hermes profiles volume.
- The previous one-role `hermes-cpo-role-skill-sync.timer` is **disabled** (definitions retained). The Wiki mirror timer remains active. These are **file synchronization timers**, not Paperclip agent execution routines or task watchdogs.
- Baseline audit before repair: four Mascot Designer files differed. Post-repair and post-timer audit: **68/68 match approved hashes; zero drift**.

### Operator commands (Ubuntu VPS)

```sh
# No write; returns 0 only for fully in-sync approved source/destination:
python3 /opt/hermes-gateway-ops/sync_profile_skills.py
# One-shot authorized role skill sync:
sudo systemctl start hermes-profile-skills-sync.service
# Inspect periodic file-only sync and source freshness:
systemctl status hermes-profile-skills-sync.timer hermes-test-wiki-sync.timer
journalctl -u hermes-profile-skills-sync.service -n 30 --no-pager
journalctl -u hermes-test-wiki-sync.service -n 30 --no-pager
# Read-only API allowlist drift check:
python3 /opt/hermes-gateway-ops/apply_gateway_api_toolsets.py
# Reapply a reviewed allowlist (does not redeploy container or touch models):
sudo python3 /opt/hermes-gateway-ops/apply_gateway_api_toolsets.py --apply
# Scoped Wiki unit tests (inside current Hermes container):
CID=$(docker ps -q --filter name=2sganhxhhnioiqh4an9g2f4k | head -1)
docker exec "$CID" /opt/hermes/.venv/bin/python -m unittest discover \
  -s /opt/data/mcp/tests -p test_wiki_scoped.py -v
# Tested role-specific MCP discovery:
docker exec -e HERMES_HOME=/opt/data/profiles/cho "$CID" \
  /opt/hermes/bin/hermes mcp test wiki_fs
```

Code and deployment files are versioned under `integrations/hermes-paperclip/wiki/` and `integrations/hermes-paperclip/roles/`. Operational on-host copies are under `/opt/hermes-gateway-ops`; the current `wiki_scoped.py` is under the persistent Hermes volume. After reviewing and merging the harness PR, sync the approved scripts with the repository's versions; avoid maintaining a separate hand-edited runtime variant.

## Test evidence (2026-11-02)

| Test | Result | Evidence |
| --- | --- | --- |
| Coolify Gateway rolling update | PASS | deployment `jy9kogkyovkl4dw00rdxh3zj`, healthy |
| 14 profile bank and config readback | PASS | 14/14 named Hindsight bank IDs and role-scoped Wiki |
| 14 API role tool policies after restart | PASS (configuration readback) | all forbidden execution toolsets absent |
| Default + historical profiles tool denial | PASS (CLI readback) | terminal/file/code/cron disabled |
| Read-only Wiki ACL and traversal unit tests | PASS | 7/7 unit tests (including cross-role denial) |
| Wiki MCP discovery | PASS | three authorized tools, tested profiles CHO/CPO/CEO |
| Live CHO Wiki read | PASS | SHA `27279ffd7450b58f2c0083958982232ca105e35d02f54c5b099057179850c0ba` |
| Full source vs mirrored Wiki Markdown | PASS | `rsync -rcn` reported no changes |
| Per-role allowed skills and SHA | PASS | 68/68, zero drift |
| Unapproved source skill revision | PASS (deny) | synthetic manifest mismatch rejected `UNAPPROVED_SOURCE_SHA` |
| Skill file sync systemd service | PASS | `ExecMainStatus=0`, new timer active |
| Anonymous access to six API profiles | PASS (deny) | six HTTP 401 responses |
| CHO native Hindsight retain → independent recall | PASS (selected profile) | Opik tool spans; test documents deleted |
| All 14 independent authenticated live agent sessions | NOT TESTED | not implied by static bank configuration |
| Cross-profile wrong-key challenge | NOT TESTED | requires authorized secret-aware testing |
| Docker process/root sandbox | NO-GO | local backend root; API execution tools are disabled as mitigation |
| Paperclip run-bound native plugin access | NO-GO | `KOMAA-1512` unresolved |
| Paperclip agent adapter migration | **DEFERRED** | 0/14; do not modify in this change |
| DeepSeek V4.1 provider | **DEFERRED** | unchanged |

Opik examples from native CHO tests: Wiki trace `01a19d38-1f27-7e46-a0ca-b76f2eb5208c`, retain trace `01a19d3b-bd4b-7065-bb1b-ef76127484d2`, independent recall trace `01a19d3c-5e80-75e6-84ff-b20984160132`. These are **Hermes CLI** execution traces, not Paperclip run-id E2E evidence.

## Rollback and safety

Before remediation, saved root-only backups:
- `/opt/hermes-profile-cutover-backup-20261102/*-config.yaml` (initial named profile configurations)
- `/opt/hermes-profile-cutover-backup-20261102/api-allowlist/*-config.yaml`
- `/opt/hermes-profile-cutover-backup-20261102/dormant-profile-lockdown/*-config.yaml`
- `/opt/data/healthcheck-backups/*-before-scoped-wiki-20261102.yaml` (persistent profile snapshots)

Do **not** blindly restore all backups: reverting the API allowlist will reopen terminal/file/code execution. For a failed rollout, stop the affected synchronization timer, inspect the change, restore only the explicitly affected reviewed file, restart the existing Coolify Gateway app and verify health, signed auth, scoped Wiki, bank IDs, Opik and post-restoration diff. Never print `.env`, secrets or tokens.

## Remaining independent gates

1. Proper Docker/remote execution sandbox, restricted UID and capabilities for any future code-executing profile. No direct network-triggered unrestricted shell.
2. Verified Paperclip-issued *run-scoped* MCP token propagation and native plugin permission enforcement (`KOMAA-1512`).
3. Separate per-agent Paperclip Vault `secret_ref`, correct agent model/provider, authorized role-scoped MCP action tools, and true cross-profile wrong-key rejection.
4. Real Paperclip issue lifecycle: assigned work → isolated branch → execution → independent review → approved release → deployed digest → readback → DONE; Opik correlated by exact Paperclip run ID.
5. Additional per-role live memory recall and negative cross-bank tests; no claims from a bank's name alone.

**Keep the existing 14 Paperclip OpenCode adapters and all their original model assignments untouched until a separately approved migration.**


### Additional regression tests and machine-readable evidence

- Role skill synchronization unit tests: **4/4 PASS** — idempotent re-sync, approved SHA-256 gating, destination symlink denial and required pin validation.
- [Bounded gateway acceptance evidence](evidence/2026-11-02-gateway-isolation.json) documents the tested and untested controls without conflating Gateway validation with Paperclip E2E.
- The current `profile-skill-allowlist.json` includes 20 immutable SHA-256 approvals for 68 profile-to-skill bindings. Changing an upstream Paperclip `SKILL.md` without independently updating the approved hash makes the systemd sync fail closed; it does **not** silently publish the revision.
