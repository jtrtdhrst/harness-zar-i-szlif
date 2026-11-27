# Native Multica / Hermes production runtime — operational decision and evidence

Date: 2026-11-27. Scope: Żar i Szlif native agent runtime and integration acceptance, not production release approval.

## Decision

Use upstream Multica v0.13.0 and upstream Hermes v0.23.4 (commit 8fc0374447313e276f6b9a2764bfc750190c966a). All 12 active Multica agents use `openai-codex/gpt-6-luna`, native profile `default`, and the root Codex OAuth store. No custom ACP bridge, role broker or promotion controller is required for this runtime. Preserve the existing security, independent-review, trusted CI, immutable-digest, release HOLD and rollback gates. The old custom Paperclip/Hermes gateway PR #225 is not evidence for the new runtime and is not part of this documentation-only change.

## Production configuration

- Native source checkout: `/srv/multica-zar/hermes-clean-20261127/data/hermes-agent`.
- Persistent Hermes data root: `/srv/multica-zar/hermes-clean-20261127/data`.
- Native `HERMES_RUNTIME_DIR`: the persistent data root's `tools` directory; both the Multica daemon and Hermes Gateway use it. Do not publish a launcher bound to a disposable task home.
- Services: `multica-daemon-zar-prod.service` and `hermes-gateway-daf685c6.service` active and enabled; user linger enabled. Native service configuration changed on 2026-11-27; pre-switch service backup retained in operator-only archive `20261127T182331Z`. Previous install retained for rollback.
- Agent instructions and bound skills are provided by Multica. Effective Hermes memories are agent-scoped; conversation SQLite databases are task-local. Shared base SOUL.md and OAuth are intentional. This is logical separation, not an OS sandbox.
- Separate Hindsight MCP bindings per agent and role-specific RepoWise bindings remain authoritative. External memory provider is disabled in the native task overlay to avoid a shared external bank.
- Native `skills.create_dir` is `/srv/multica-zar/hermes-learned-skills/${MULTICA_AGENT_ID}`; `skills.write_approval: true`. Automatic review is enabled; memory and skill nudge intervals set to 1 for bounded validation. The skill interval is read by installed source despite a CLI unknown-key warning. Reassess cadence/cost before sustained production workloads. Do not assume a standalone Gateway without Multica identity resolves to an agent-specific directory.

## Acceptance evidence

Native issue ZARI-306: https://multica.zariszlif.pl/zar-i-szlif/issues/01a20e4c-cfa8-718f-9a3d-d3f73f359cbe

| Test | Evidence | Result |
|---|---|---|
| UI QA inference | run 01a21e1d-91bb-7886-ba44-5814905f55ef | PASS |
| Harness Engineer Hindsight / RepoWise | run 01a21e1e-46cb-7938-9b84-2b5d4b8b2cdd, Harness scope | PASS read |
| Engineer role + Hindsight / RepoWise | run 01a21e22-380b-7ada-8539-87779d1b322c, Product scope | PASS read |
| Native memory add and removal | runs 01a21e23-bd30-7ecb-b72a-88c49b70e052 and 01a21e24-956d-71dc-8dab-c8c5bd312ca7; marker absent in two other tested stores | PASS |
| COO context and release gate recognition | run 01a21e27-3e0b-70bf-96d8-8f8d6f071b94 | PASS |
| Skill approval staging | run 01a21e2d-a97d-7ad6-aa48-2a11c536e0b9; pending db86d8dd; exact synthetic-only proposal approved via native handler | PASS |
| Post-migration skill retrieval | run 01a21e3f-d258-7899-8008-15237b927b68; actual skill_view returned synthetic skill | PASS |
| Second role reports marker absent | run 01a21e40-b2d1-780e-94a4-bd8951447fa4; used read_file instead of requested skill tools; CLI skills list did not show marker even for owner | INCONCLUSIVE for strict negative catalog test |
| Launcher after two actual post-switch runs | interpreter remains in persistent tools directory; both services active | PASS |
| Hindsight unauthenticated and invalid synthetic credential requests | 84/84 rejected with HTTP 404 at existing gateway; no knowledge returned | PASS for unauthenticated/invalid credentials only |
| RepoWise index freshness | Harness e44952c97397f78fc47e8062793b4f8fc9ece1bc; Product c2490d7a32eedf5ccdae6f2fbd94eaa3ccf3ccd9; both matched main at inspection | PASS |
| Automatic Hermes Background Review / Curator | zero observed completions in inspected default-profile overlays | NOT VERIFIED |
| GitHub Ops agent credential | AUTH_FILE_EXPIRED; existing source requires separately minted scoped token file, old refresher retired | FAIL |
| Coolify MCP read | connector list_applications failed internally; container health does not prove authorization or delivery | FAIL / not verified |
| Product release | published panel commit 11a3ebbb8a0a034316eeb31deb7367b38571f0f8 versus main c2490d7a32eedf5ccdae6f2fbd94eaa3ccf3ccd9; compare diverged (10 ahead, 1 behind) | FAIL |
| Queue | native execution watchdog paused; runtime tests are not production delivery | NOT READY |

## Remaining admission criteria

1. Restore supported scoped GitHub credential lifecycle without reinstating retired custom refresh automation or weakening authorization. Do not enable writes outside the existing approved policy.
2. Verify actual automatic review execution, role-specific skill discovery across independent tasks, and authorized bank/repository separation using scoped synthetic data; do not equate a shared volume or prompt-only constraint with enforcement.
3. Reconcile existing ZARI-263 / ZARI-298 / ZARI-307 and existing PRs #204 / #246 / #225 where applicable. No duplicate implementation branches. Maintain exact-head independent review and release authorization.
4. Verify trusted CI, canonical source/build root, native automatic delivery, immutable image/source parity, positive/negative production acceptance and rollback. Only then re-enable autonomous production watchdog under the existing rules.
5. Index this reviewed document from main using RepoWise's supported repository indexing workflow and verify retrieval. This PR is documentation only and is not evidence of indexing or delivery.

Current verdict: native runtime restored and tested; full production delivery and automatic learning acceptance remain incomplete. No custom upstream code modifications, no release-gate bypass.
