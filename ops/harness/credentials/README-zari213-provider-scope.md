# ZARI-213 — provider-scoped Hermes model .env projection

Security scope: harden global model-credential filesystem paths without breaking the provider-specific bootstrap. Shared Codex OAuth auth.json and same-provider token reuse are STILL unresolved. This change does not qualify the parent isolation HOLD for release.

## Causal native evidence
2026-11-19 real CHO native TOOL_USE/TOOL_RESULT one-shot only opened/closed files; own CHO profile ALLOWED, CTO profile and shared repo DENIED (errno 13), global auth.json and global .env BOTH ALLOWED. No credential bytes read.
14 role profiles currently link .env to same global OPENCODE_GO_API_KEY. Six roles are openai-codex; eight are opencode-go. Old Landlock launcher granted global auth.json and .env READ to everyone.

## Source change
role_env_projector.py runs unprivileged as multica-zar. It preflights the exact provider/role mapping, single-key global .env schema, ownership and symlink targets; it atomically materializes private 0600 per-role env files, leaving Codex roles without the unrelated OpenCode key. It never prints credential values. All eight OpenCode roles still use a common provider key; uniqueness is not claimed.
Landlock policy checks normalized MULTICA_AGENT_NAME against persisted HERMES_HOME role, rejects non-approved role mapping, removes global .env READ for all roles and global auth.json READ for OpenCode roles. Codex roles retain shared OAuth access until a separate trusted credential broker exists. Auth authority must not be inferred from task-writable profile YAML.
Existing role canary now sets its actual agent role; new native kernel provider canary performs only open/close and records denial errno, without reading contents.

## Tests
Operator unprivileged synthetic: role_env_projector 5/5 PASS; staged kernel Landlock CHO 5/5 PASS and Engineer 5/5 PASS. Non-mutating production preflight validated all 14 role provider configs. No live .env, launcher or service changed as part of candidate tests.

## Controlled rollout and rollback
1. Independent exact-SHA CTO review of source, filesystem boundaries and tests, followed by CI.
2. Back up role .env symlink metadata and root-owned Landlock launcher; stage approved files. Run projector as multica-zar (never as root) to replace only 14 validated symlinks atomically. Verify role files are 0600, no links to shared .env, provider startup and rollback path.
3. Only then atomically install approved root-owned Landlock launcher; validate native two-role TOOL_USE/TOOL_RESULT positive own-profile and negative global/foreign opens, provider inference, task resume and gateway health. If negative, restore launcher and role .env link metadata in controlled order.
4. Existing root-owned Hermes key refresh timer may execute the projector as multica-zar through a reviewed ExecStartPost; no duplicate timers/watchdogs.
5. Keep ZARI-213 BLOCKED: role-specific Codex OAuth broker, no shared token across roles, historical session overlays and native full-cycle release remain separate acceptance requirements.

No raw tokens or secret content is included in this repository.
