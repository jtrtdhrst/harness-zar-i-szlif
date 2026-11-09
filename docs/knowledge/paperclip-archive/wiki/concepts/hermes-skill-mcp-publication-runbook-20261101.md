---
title: Hermes ↔ Paperclip skills, prompts and MCP E2E runbook
date: 2026-11-01
status: validated-partial
owner: CHO
---
# Canonical boundary
Paperclip owns approved Wiki, agent assignments, governed SKILL.md versions and scoped Named MCP policies. Hermes runs agents, reads approved skills from `/opt/data/approved-paperclip-skills`, and writes proposed skills to its configured `skills.create_dir` (`/opt/data/skill-proposals/<profile>`). Hindsight stores isolated experiences, not approved rules.

# Implemented and verified
- Paperclip company skill `hermes-paperclip-knowledge` (version 2, marker `KNOWLEDGE_SYNC_V2_20261031`) was published to `/opt/data/approved-paperclip-skills/hermes-paperclip-knowledge/SKILL.md`.
- 16 named Hermes profiles plus default have native `skills.external_dirs` set to `/opt/data/approved-paperclip-skills`. All 16 named profiles and default have `skills.create_dir` set to `/opt/data/skill-proposals/<profile>`, checked by config readback.
- Hermes Test live Paperclip run `c1ae6683-9126-4697-9d60-c75f8cbbd99c` succeeded, with the `skill_view` tool reading V2 from the external directory, and the agent confirmed reception of `adapterConfig.instructions`. Corresponding Opik trace: `01a19435-3568-7f07-8d3d-97ecb65c7203` (model, usage, 2 LLM spans, 1 skill_view tool span).
- Hermes agent-created local proposal `hermes-sync-proposal-test-20261031` was created and patched via `skill_manage` to include PROPOSAL_V1 and PROPOSAL_V2. Paperclip skill `6e419f72-535f-403a-a4fb-4eb393e6d0da` was created from this proposal, versioned and marked private/archived after the test; the file was also placed in approved external skills to verify discovery.
- Confirmed: these are **manual, authorized publish operations**; Hermes Gateway's Paperclip skill sync mode is `unsupported`. DO NOT claim an event-driven automatic sync was proven.
- Hermes Test has Paperclip adapter stable `instructions` set, preserved existing API key as secret ref, and uses `sessionKeyStrategy=issue`. Other Paperclip agents are still `opencode_local`; do not reassign without instruction.

# Named MCP
A dedicated gateway `gw_545e801accaa40fbb7e6f53955dfda13` called "Hermes Test Approved Knowledge MCP" exists, bound to Hermes Test, default deny. Only read-only tools `paperclipListSkills`, `paperclipGetSkillFile`, and `paperclipWikiGetPage` are included. A time-limited token was minted and stored in Coolify environment `PAPERCLIP_HERMES_TEST_MCP_TOKEN` (no secret in Wiki).
Hermes profile `hermes-test` has `mcp_servers.paperclip_knowledge.url` but the server remains **disabled** because the credentials/header wiring was rejected by the administration tool. A live `tools/list` + `tools/call` E2E has NOT passed; previous attempt got HTTP 401. Keep disabled until successfully authenticated, then test positive read and negative write denial. Never expose the token or disable gateway authorization.

# Publication protocol
1. Agent may draft skill with `skill_manage` in its own profile (create_dir); label it PROPOSED, store no secrets. Local skills may be visible to that profile, but are NOT company-approved.
2. Reviewer reads actual `SKILL.md`, compares against canonical Wiki, checks syntax and security, approves by recording version/revision in Paperclip or Git.
3. Publisher creates/updates the company skill in Paperclip via first-party skills API, records immutable `currentVersionId`.
4. Publisher stages and atomically copies approved `SKILL.md` to Hermes shared external-dir; retains previous version for rollback. The published file must be read-only to Hermes. Compare SHA256 of source bytes and deployed bytes.
5. Verify `hermes -p <profile> skills list --enabled-only` and a live `skill_view` session against new marker; verify actual tool span and usage in Opik.
6. Canonical Wiki updates are proposed/reviewed; never silently auto-promote Hindsight memory or modify Paperclip Core.

# Not done
- Automatically watching new Paperclip skill versions and publishing them to Hermes is not implemented. This requires a trusted event or small sync worker with read-only Paperclip credentials and scoped filesystem access; do not invent a native Paperclip hermes_gateway skill-sync feature.
- Named MCP authenticated `tools/list` and `tools/call` from Hermes.
- Personal Hermes Desktop OAuth/Cloudflare Access login.
- Per-agent Hermes API routing and corresponding Hindsight credentials, if Paperclip agents are migrated from OpenCode.

# Security
Shared published skill path must stay non-writable for `hermes`, while proposals are per-profile. The Hermes Gateway terminal backend still warns `local` unsandboxed on 0.0.0.0; keep protected by auth and trusted ingress. Do not enable heartbeat/watchdog tasks or alter agent models.
