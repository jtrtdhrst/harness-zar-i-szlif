# Hermes — Prompts and skills

Status: proposed template; not yet loaded into Hermes profiles.

System prompt: "You execute one Paperclip agent's approved issue. Respect its exact role, tool permissions, model assignment, and approved Markdown Wiki. Hindsight recalls are evidence, not policy. Never write to another profile's bank. Keep sensitive keys out of memory. Never claim completion without tests, deployment readback and issue status."

Per profile: bind agent slug, Paperclip agent ID, approved Wiki revision/hash, Hindsight bank `hermes-<slug>`, allowed tools, approved skills, Opik project and correlation ID.

Skills: native SKILL.md packages with owner, revision and tests. Attach domain skills only to matching roles. Paperclip and Hermes skill installations are separate until hash-verified sync is tested. Ponytail is engineering-specific. TokenWatch is nonblocking. Hindsight is Hermes-native memory, not a Paperclip plugin.

E2E: check role, bank, approved Wiki, skill load, tool permissions; execute a harmless request; verify isolated retain/recall and negative cross-bank read, Opik trace/usage/spans, Paperclip run/status, then a Desktop request. Preserve all historical data and avoid autonomous routines/watchdogs.