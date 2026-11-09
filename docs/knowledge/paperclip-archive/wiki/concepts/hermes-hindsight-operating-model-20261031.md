---
title: Hermes Gateway / Hindsight Cloud operating contract
type: concept
status: approved-owner-architecture
date: 2026-10-31
---

# Runtime boundaries and source of truth

Paperclip is the orchestration/control plane (issues, assignments, permissions, reviews and Named MCP Gateway). Hermes Gateway is the execution plane. Hermes Desktop is a remote client of the same Hermes Gateway, not a separate source of truth. Vectorize.ai Hindsight Cloud is the managed long-term memory provider; it is **not Cloudflare Vectorize**. Opik handles telemetry. Coolify manages infrastructure.

Do not deploy a Hindsight Paperclip plugin or modify Paperclip Core for this. Hermes must use its native Hindsight memory provider; Paperclip calls Hermes via its official `hermes_gateway` adapter. Prefer native configuration and existing plugins to custom glue.

# Knowledge and memory authority

- **Canonical Wiki**: reviewed versioned Markdown documents in the Paperclip Wiki/Git tree; agent instructions, accepted decisions and operating procedures are authoritative.
- **Hindsight**: agent-specific episodic/semantic experiences, implementation feedback, observations and previously resolved incidents. A memory is evidence, never an approved decision.
- Wiki -> Hindsight: ingest only approved and versioned documentation, labelled with source path, hash and revision. Updating Markdown must not automatically rewrite agent memory; prevent feedback loops.
- Hindsight -> Wiki: propose changes for review; no unattended promotion or rewriting canonical Wiki.
- **Prompts**: role-bound SOUL.md / AGENTS.md or managed templates, version controlled separately from episodic memories.
- **Skills**: reusable SKILL.md instruction packages with version, owner, scope and tests. Paperclip desired skill sets and Hermes profile skill folders are separate installations until an explicit supported synchronization is tested.
- **Tools**: Named MCP Gateway in Paperclip; tool authorization belongs to Paperclip, not Hindsight. Do not copy privileged MCP credentials into unrelated Hermes profiles.

# Profile / bank isolation

Create a dedicated Hermes profile and Hindsight bank per Paperclip agent. Names follow `hermes-<agent-url-key>`, e.g. `ceo` -> `hermes-ceo`. Explicitly set native Hindsight `bank_id` per profile. Never import all profiles into a shared bank. A global/default legacy bank `hermes` is retained as read-only historical data until a separately approved migration. Test write, recall, and negative cross-bank recall per profile before claiming isolation.

# Remote and access

- Paperclip API backend: `hermes-poc.zariszlif.pl` -> port 8642 via Cloudflare Tunnel; maintain Bearer authorization.
- Hermes Desktop backend: `hermes-desktop.zariszlif.pl` -> port 9119 via Cloudflare Tunnel; Desktop connects through Settings -> Gateways -> Remote gateway.
- Public Desktop access needs Hermes-compatible OAuth/OIDC or a VPN/trusted-network arrangement. A Cloudflare Access service-token-only policy is not compatible with the ordinary Hermes Desktop sign-in flow. Do not replace it with an unauthenticated bypass or expose unsandboxed terminal access.
- Password-only Hermes Dashboard is suitable only for a private trusted/VPN network. Ensure its signing secret is persistent; do not store actual credentials in Wiki.
- One Hermes runtime remains the system of record. Desktop and Paperclip sessions share the agent profile's own memory, but should have separate session/issue identities.

# Definition of Done

1. Gateway stable across restart; health and authenticated API readback.
2. Every target profile has native Hindsight configured, `bank_id` verified and an isolated positive/negative memory test.
3. Paperclip -> Hermes actual agent run succeeds with correct routing, permissions and bounded tool execution.
4. A real Hermes request produces an Opik trace with agent, model, usage and span hierarchy verified by readback.
5. Desktop remote URL supports authenticated sign-in and chat; no Cloudflare 401/403 barrier.
6. Wiki, prompts and skills are present in runtime, versioned, and loaded in real test sessions.
7. No unapproved model reassignment, Paperclip Core modification, autonomous watchdog/heartbeat, or destructive data cleanup.

As of this page's creation, these items are acceptance criteria; the existence of this page alone does not claim they passed.

## Verified native multi-profile API routing (2026-10-31)

Hermes v0.22.5 serves named profiles under `/p/<profile>/v1/...` only when `gateway.multiplex_profiles=true` and the named profile has its own `API_SERVER_KEY` in `profiles/<profile>/.env`. A default API key on that prefix returns HTTP 401. Paperclip's current built-in `hermes_gateway` adapter exposes `apiBaseUrl`, `apiKey`, `sessionKeyStrategy`, `headers` and `instructions` but no explicit Hermes profile-selector field. A Paperclip agent pointing at the unprefixed gateway URL runs as Hermes `default` even when the Paperclip agent itself has a different name. Do not claim per-agent Hindsight isolation until an actual routed Paperclip run proves its profile and bank.

Verified evidence: Hermes agent chat returned `CHAT_E2E_OK` on 2026-10-31, but identified Hermes profile `default`. Two actual Opik traces exist, including a Paperclip-driven trace with four LLM spans and three tool spans, model `gpt-6-luna`. Hermes Test routed profile is **not** yet fixed. Newly created Hindsight banks and `bank_id_template=hermes-{profile}` are not by themselves proof of routed isolation.

Hermes v0.22.5 plugin dependency manager can conflict on same-named buildable plugins copied across multiple profiles. The non-engineering profiles keep TokenWatch disabled, while the default retains it. Ponytail is opt-in only for engineering profiles; ordinary Desktop/API prompts must not be rewritten with its coding persona. Prefer upstream fixes; no Paperclip Core changes or custom gateway router.

Cloudflare Access service-token-only policy on `hermes-desktop.zariszlif.pl` blocks ordinary Hermes Desktop; it cannot inject custom Access headers. Do not bypass the Access boundary. Public remote mode requires supported OAuth/OIDC with completed human account registration, or a private trusted VPN network and Hermes Basic Auth.

## Skills, prompts and MCP — verified integration status (2026-10-31)

- Paperclip company skill `hermes-paperclip-knowledge` id `4dfdb571-ff2f-4ba4-95c5-8896fb011e27` was created, edited, and revision 2 `6552a169-e95a-47d3-8737-fed3041e5931` read back with test marker `KNOWLEDGE_SYNC_V2_20261031`.
- Publication target in Hermes: `/opt/data/approved-paperclip-skills/hermes-paperclip-knowledge/SKILL.md`. Verified length 1008 bytes, SHA-256 `b948aac94f90f9ca00aa2944bf7f82386a302b00525b41d992e269a33f8b0fa8`; owned/permissioned as read-only for Hermes.
- Hermes config `skills.external_dirs` includes `/opt/data/approved-paperclip-skills` in all 16 named profiles plus default. User-local skills remain writable and higher precedence, so duplicate names must be audited.
- Paperclip Hermes Test `adapterConfig.instructions` carries stable approved-Wiki-over-Hindsight governance and survived a non-replacing atomic patch; existing API secret ref, session strategy, and model were preserved. Actual Paperclip run `c1ae6683-9126-4697-9d60-c75f8cbbd99c` succeeded: `skill_view` read the external SKILL.md and responded `KNOWLEDGE_SYNC_V2_20261031`. Opik trace: `01a19435-3568-7f07-8d3d-97ecb65c7203`.
- Actual Paperclip run `28826baa-269e-466b-affc-69bb65cce16e` succeeded: Hermes `skill_manage` created then edited local skill `/opt/data/skills/hermes-sync-proposal-test-20261031/SKILL.md`, and `skill_view` verified proposal v1/v2. Opik trace `01a19436-e653-7078-9bc0-812df76bf348`. No automatic publication was performed.
- Named Paperclip MCP Gateway `gw_545e801accaa40fbb7e6f53955dfda13` and profile `161e3d86-9e50-43cf-b8c9-3961655c3187` are active, with default deny and only `paperclipListSkills`, `paperclipGetSkillFile`, `paperclipWikiGetPage` read-only entries. Token valid through 2026-11-30 is stored in Coolify environment as `PAPERCLIP_HERMES_TEST_MCP_TOKEN`, without raw value in Wiki. Hermes test profile has MCP URL configured but **the Authorization header was blocked by management tooling and is not installed**; HTTP 401 verified. MCP server was disabled in Hermes profile to prevent repeated failed connects. Do not claim MCP `tools/list` / `tools/call` E2E success.
- Because Paperclip Hermes adapter skill sync mode is `unsupported`, publication from Paperclip to Hermes was performed as an explicit controlled copy, not an automatic event/subscription. An automatic publisher still needs a supported and approved bridging mechanism; do not claim real-time synchronization.
- Temporary invalid/partial skill files were moved to `/opt/data/backups/`, not deleted. Existing agent model assignments, Paperclip Core, routines and watchdog settings remained unchanged.

### Release contract

Agent creates or patches local proposal using `skill_manage` → review/approval in Paperclip → new version in Paperclip managed skill library → explicit publication of approved SKILL.md to the read-only Hermes shared directory → verify source hash/content and Hermes `skill_view` on the target profile → verify Opik run and retain a rollback copy. Until an automatic publisher is implemented and authenticated, publication is **operator-triggered**. Never let an unreviewed agent write directly to the approved shared directory.
