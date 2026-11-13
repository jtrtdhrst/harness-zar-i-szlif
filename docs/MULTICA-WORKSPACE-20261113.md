# Multica workspace — verified state (2026-11-13)

This is the current-state record for the `Żar i Szlif` workspace
(`28378cc8-2c3a-4f8e-af1c-63e308407b17`). It replaces migration-era notes as
the source of truth. Every fact below was read back from the live API or host
on 2026-11-13; timestamps are UTC.

## Runtime decision

- **Hermes is the production runtime for all 14 agents.** Runtime
  `2c84d3ef-7bf7-4e1c-b81a-3078d9e5512c`, `hermes acp`, online, last seen
  2026-11-13T18:38Z.
- **OpenCode runtime `2a9b818b-ebb3-4ab1-b2d1-3dd4501f3272` stays online with
  no agents bound.** It is a warm standby only. Moving any agent requires a
  per-agent E2E run on that runtime first; the 14/14 canaries were executed on
  Hermes and do not transfer.
- Effective model for every agent: `opencode-go:deepseek-v4.1-flash`. The
  original `openai/gpt-6-luna` is historical context only; it was unavailable
  in the runtime catalog and is the recorded fallback reason. No agent was
  switched on the strength of a model name.

## Agents

All agents: visibility `private`, permission mode `private`, runtime-bound to
Hermes, 6 `custom_env` keys (OTEL), `custom_args: ["-p", "<profile>"]`.

| Agent | Concurrency | MCP servers | Skills |
|---|---:|---|---:|
| CEO | 1 | hindsight-ceo, repowise | 12 |
| CHO | 2 | hindsight-cho, repowise | 8 |
| CMO | 1 | emailens, hindsight-cmo, mautic, repowise | 12 |
| COO | 1 | hindsight-coo, repowise | 11 |
| CPO | 1 | comfyui, hindsight-cpo, repowise | 11 |
| CTO | 2 | hindsight-cto, repowise | 9 |
| Designer | 2 | hindsight-designer, plasmic, playwright, repowise | 8 |
| Email Creative | 2 | emailens, hindsight-email-creative, mautic, repowise | 9 |
| Engineer | 1 | hindsight-engineer, repowise | 10 |
| Harness Engineer | 1 | hindsight-harness-engineer, repowise | 11 |
| Lifecycle Ops | 2 | emailens, hindsight-lifecycle-ops, mautic, repowise | 9 |
| Mascot Designer | 1 | comfyui, hindsight-mascot-designer, repowise | 13 |
| MCP Engineer | 2 | hindsight-mcp-engineer, repowise | 10 |
| UI QA | 2 | hindsight-playwright, repowise | 8 |

Skill changes applied on 2026-11-13: CPO received the three mascot skills,
CHO `kompas-harness-environment-specialist`, CEO and CTO
`acceptance-contract-cross-model`; `mascot-style-2-pipeline` was removed from
Engineer, Designer and UI QA, `host-product-mcp-delivery` from CHO,
`paperclip-langfuse-observability` from COO and MCP Engineer, and
`cto-source-bundle-attachments` from CTO. Every assignment was read back.

Telemetry (all 14): `HERMES_OTEL_CAPTURE_CONTENT=false`,
`HERMES_OTEL_LOGS_ENABLED=false`, HTTPS endpoint
`https://opik.kompaszbiorek.pl/api/v1/private/otel`, one Opik project
`multica-zar-i-szlif`, per-agent service name. Content capture stays off until
a separate, explicit decision. Mascot Designer's service name was corrected to
`zar-i-szlif-hermes-mascot-designer`.

## MCP inventory

Registered in the workspace (16): `hindsight-ceo`, `hindsight-cho`,
`hindsight-cmo`, `hindsight-coo`, `hindsight-cpo`, `hindsight-cto`,
`hindsight-designer`, `hindsight-email-creative`, `hindsight-engineer`,
`hindsight-harness-engineer`, `hindsight-lifecycle-ops`,
`hindsight-mascot-designer`, `hindsight-mcp-engineer`, `hindsight-ui-qa`,
`playwright-local`, `repowise`.

Additional per-agent servers are declared inline in `mcp_config`
(`playwright`, `plasmic`, `mautic`, `emailens`, `comfyui`) because they need
per-agent transport URLs. `product-host` (`https://mcp.zariszlif.pl`) is **not**
registered for any agent: it needs a Supabase JWT and is exercised by the
controller canary instead (`/usr/local/libexec/mcp_host_live_canary.py`,
12/12, evidence in `/var/lib/multica-canary/mcp-host.json`). Do not add a
long-lived product JWT to an agent profile without a scoped-token design.

## Squads

| Squad | Leader | Members |
|---|---|---|
| Leadership — Żar i Szlif | CEO | CEO, CMO, COO, CTO, CHO, CPO |
| Engineering — CTO | CTO | CTO, Engineer, MCP Engineer, Designer, UI QA |
| Growth & Lifecycle — CMO | CMO | CMO, Email Creative, Lifecycle Ops |
| Harness — CHO | CHO | CHO, Harness Engineer |
| Mascots — CPO | CPO | CPO, Mascot Designer |

A squad routes a mention to its leader; it is not an enforced `reportsTo`
hierarchy. The leader must create sub-issues explicitly. Cross-squad acceptance
(e.g. CMO/UI QA accepting mascot work) is a task assignment, not a squad
membership.

## Workflow and Done gate

`Default` workflow (both projects): `backlog → todo → in_progress → in_review
→ done`, plus `blocked` and `cancelled`. `in_review` is handled by CTO. When
CTO authored the change, an independent CHO review is required; this is an
instruction-level rule because Multica supports one handler per status.

The independent Done gate (`ops/multica-done-gate`) reverts two objectively
checkable violations: a producer approving its own work, and a `Release ...`
issue closed without a healthy promotion record (or docs-only evidence). It
never rewrites history (bootstrap watermark) and reverts each issue once.

## GitHub delivery

- Repositories: `miloszspyrka-code/zar-i-szlif` (product) and
  `miloszspyrka-code/harness-zar-i-szlif` (infrastructure).
- Credentials: root broker `multica-git-credential-broker.py` over a unix
  socket, `SO_PEERCRED` + daemon process-tree check, roles `implementer`,
  `reviewer`, `release` in `/etc/multica-git-credential/agent-roles.json`.
  Tokens are installation tokens for App 5398752, scoped to exactly those two
  repositories, TTL about one hour, never printed by the broker.
- **Broker E2E proven 2026-11-13**: Harness Engineer (`c1c8b457…`,
  `implementer`) pushed `chore/credential-broker-e2e-20261113` and opened PR
  #102 at head `5e2f3771cc708212ea21315d21594313d7a8f973`; broker log shows
  three `credential ... role=implementer repo=harness-zar-i-szlif` grants for
  that agent, and PR readback matched local HEAD. Evidence: ZARI-201.
- Branch protection and rulesets are **not available** on the current GitHub
  plan (`403 Upgrade to GitHub Pro`, `administration=read` denied). Compensating
  controls: role-scoped broker, native exact-SHA gate before deploy,
  `ci-approved` advanced only by the controller, pre-push hook, and the Done
  gate. These are controls, not a substitute for real rulesets: an implementer
  token still carries `contents:write` for both repositories.

## Known gaps (open)

1. **No server-side branch protection** — the primary structural gap; unblock
   with GitHub Pro or public repositories, then require PR, review, checks and
   restrict `ci-approved`.
2. **Duplicate dispatch on status transitions** — moving an issue to
   `in_review` while a run is active queues a second run; concurrency 2 makes
   both start (observed on ZARI-200). Cancel the queued duplicate or wait for
   the active run.
3. **Run status lags issue status** — a run can stay `running` after its result
   comment is posted (observed on ZARI-201). Do not treat `running` alone as an
   execution failure.
4. **No automatic retry** — six runs failed on the old `gpt-6-luna` selection
   and nothing retried them; `max_attempts=2` is not applied by the runtime.
5. **Stale backlog** — 16 migration issues in `in_review` for 76 h and 11
   legacy `KOMAA` tombstones in `blocked` with no assignee. Triage them
   explicitly; do not mass-close.
6. **Mautic/Emailens** are transport-green but data-empty (0 campaigns, 0
   segments).
7. **Mascot image generation** remains blocked: hosted image tool account is on
   `free`, no OpenAI/fal key, no local diffusion weights.
8. **Public edge had no watchdog** — `coolify-caddy` stayed down for 33 minutes
   on 2026-11-13 after a Docker daemon restart because a referenced network was
   missing. It was restored manually. A watchdog draft exists in PR #103 but is
   **not installed**: it needs a consecutive-failure threshold and an alert
   channel before it may restart the public edge.

## Verification commands

```bash
curl -s https://panel.zariszlif.pl/__release.json
curl -s https://mcp.zariszlif.pl/health
sudo python3 /usr/local/libexec/mcp_host_live_canary.py
sudo python3 /usr/local/libexec/multica_done_gate.py --self-test
python3 ops/multica-done-gate/multica_done_gate.py --dry-run
journalctl -u multica-git-credential-broker -n 20
```
