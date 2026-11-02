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
