# Multica workspace — verified state (read 2026-11-13, re-verified 2026-11-17)

This is the current-state record for the `Żar i Szlif` workspace
(`28378cc8-2c3a-4f8e-af1c-63e308407b17`). It replaces migration-era notes as
the source of truth for what the workspace *is*.

Every fact below was read back from the live Multica API, GitHub or the host.
The date in each section heading is when that read happened; timestamps are UTC.
**A statement is evidence only for the thing it cites.** Sections stamped
2026-11-17 were re-read on 2026-11-17 between 12:47Z and 12:52Z. Sections that
still carry a 2026-11-13 stamp were not re-read and must not be used as proof of
current state.

## Runtime decision (2026-11-17)

Four runtimes are online, two per host daemon. **Hermes is the production
runtime; OpenCode is a warm standby with no agents bound.**

| Runtime | Provider | Daemon | `max_concurrent_tasks` | Agents bound |
|---|---|---|---:|---:|
| `2c84d3ef-7bf7-4e1c-b81a-3078d9e5512c` | Hermes | `01a1c56a-9c0e-7469-ad7f-f12bf19d6279` | 2 | 12 |
| `6867e6a2-691e-4d99-b3fc-05488ef61726` | Hermes | `01a1d6e8-4639-7187-bd04-467010d3d84e` | — | 2 |
| `2a9b818b-ebb3-4ab1-b2d1-3dd4501f3272` | OpenCode | `01a1c56a-9c0e-7469-ad7f-f12bf19d6279` | — | 0 |
| `2d4427dc-22a4-4e50-a784-9e5b5e488d2a` | OpenCode | `01a1d6e8-4639-7187-bd04-467010d3d84e` | — | 0 |

All four report `status: online`, `runtime_mode: local`, `visibility: private`,
same device (`VPS-Zar-i-Szlif`), `last_seen_at 2026-11-17T12:48:04Z`. Hermes is
`v0.22.5 (2026.9.24) · upstream bf0203a7`; the OpenCode daemons report `1.19.5`;
client CLI `0.8.1`. Source: `multica runtime list --output json`.

Moving an agent to an OpenCode runtime requires a per-agent E2E run on that
runtime first. The original canaries were executed on Hermes and do not transfer.

**Model distribution (2026-11-17):** 5 of 14 agents run
`openai-codex:gpt-6-luna` (CEO, CHO, CMO, CPO, CTO); the other 9 run
`opencode-go:deepseek-v4.1-flash`. This differs from the 2026-11-13 readback,
where all 14 reported `deepseek-v4.1-flash`. The record states the observed
distribution only — it is not a statement of intent, and any future change
needs its own per-agent run evidence.

## Agents (2026-11-17)

All 14: `visibility: private`, `permission_mode: private`,
`runtime_mode: local`, `custom_env_key_count: 6`, `custom_args: ["-p", "<profile>"]`,
`mcp_config: null` with `mcp_config_redacted: true`.

| Agent | Concurrency | Model | Runtime | Workspace MCP servers | Skills |
|---|---:|---|---|---|---:|
| CEO | 1 | gpt-6-luna | `2c84d3ef` | hindsight-ceo | 12 |
| CHO | 2 | gpt-6-luna | `2c84d3ef` | hindsight-cho, repowise-harness | 9 |
| CMO | 1 | gpt-6-luna | `2c84d3ef` | hindsight-cmo, repowise-product | 12 |
| COO | 1 | deepseek-v4.1-flash | `2c84d3ef` | hindsight-coo, repowise-product | 12 |
| CPO | 1 | gpt-6-luna | `2c84d3ef` | hindsight-cpo, repowise-product | 11 |
| CTO | 2 | gpt-6-luna | `2c84d3ef` | hindsight-cto, repowise-product | 12 |
| Designer | 2 | deepseek-v4.1-flash | `2c84d3ef` | hindsight-designer, repowise-product | 8 |
| Email Creative | 2 | deepseek-v4.1-flash | `2c84d3ef` | hindsight-email-creative, repowise-product | 9 |
| Engineer | 1 | deepseek-v4.1-flash | `2c84d3ef` | hindsight-engineer, repowise-product | 11 |
| Harness Engineer | 2 | deepseek-v4.1-flash | `2c84d3ef` | hindsight-harness-engineer, repowise-harness | 12 |
| Lifecycle Ops | 2 | deepseek-v4.1-flash | `6867e6a2` | hindsight-lifecycle-ops, repowise-product | 9 |
| MCP Engineer | 2 | deepseek-v4.1-flash | `6867e6a2` | hindsight-mcp-engineer, repowise-harness | 11 |
| Mascot Designer | 1 | deepseek-v4.1-flash | `2c84d3ef` | hindsight-mascot-designer, repowise-product | 13 |
| UI QA | 2 | deepseek-v4.1-flash | `2c84d3ef` | hindsight-ui-qa, playwright-local, repowise-product | 8 |

The **Workspace MCP servers** column is `multica agent mcp list <agent-id>` —
the authoritative per-agent assignment readback — not `mcp_config`. Inline
per-agent servers are not listed anywhere in this document because they cannot
be read back: `multica agent get` returns `mcp_config: null` and
`mcp_config_redacted: true` for every agent, and an agent-run principal gets
`403` from `multica agent env get`. Any server added inline rather than through
the workspace library is therefore **unverified**.

Skill assignments re-read on 2026-11-17 still match the 2026-11-13 moves: CPO
holds the three mascot skills (`mascot-anatomy-qa`, `mascot-reference-director`,
`zar-i-szlif-mascot-appearance`); CHO holds `kompas-harness-environment-specialist`;
CEO and CTO hold `acceptance-contract-cross-model`; `mascot-style-2-pipeline` is
absent from Engineer, Designer and UI QA; `host-product-mcp-delivery` is absent
from CHO; `paperclip-langfuse-observability` is absent from COO and MCP Engineer;
`cto-source-bundle-attachments` is absent from CTO.

Telemetry (2026-11-13 readback, **not** re-read on 2026-11-17 because the values
are not readable by an agent principal; only the key count — 6 per agent — was
re-verified): `HERMES_OTEL_CAPTURE_CONTENT=false`,
`HERMES_OTEL_LOGS_ENABLED=false`, HTTPS endpoint
`https://opik.kompaszbiorek.pl/api/v1/private/otel`, one Opik project
`multica-zar-i-szlif`, per-agent service name (Mascot Designer corrected to
`zar-i-szlif-hermes-mascot-designer`). Content capture stays off until a
separate, explicit decision.

## MCP inventory (2026-11-17)

Registered in the workspace (**17**): `hindsight-ceo`, `hindsight-cho`,
`hindsight-cmo`, `hindsight-coo`, `hindsight-cpo`, `hindsight-cto`,
`hindsight-designer`, `hindsight-email-creative`, `hindsight-engineer`,
`hindsight-harness-engineer`, `hindsight-lifecycle-ops`,
`hindsight-mascot-designer`, `hindsight-mcp-engineer`, `hindsight-ui-qa`,
`playwright-local`, `repowise-harness`, `repowise-product` — all transport
`http` (`multica workspace mcp list --output json`). The former single
`repowise` entry is now split into `repowise-harness` (CHO, Harness Engineer,
MCP Engineer) and `repowise-product` (everyone else). CEO is assigned no
RepoWise server.

`product-host` (`https://mcp.zariszlif.pl`) is **not** registered for any agent:
it needs a Supabase JWT and is exercised by the controller canary instead
(`/usr/local/libexec/mcp_host_live_canary.py`, root-only). Readback
2026-11-17T12:47Z: `/var/lib/multica-canary/mcp-host.json` → `ok: true`,
12/12 checks passing (login, initialize, `tools/list`, list, get, equality
filter, multi-word query, 401 no-token, 401 tampered token and the rest),
`failures: []`, `sha e5880d53e9bb9f0dc1b201ec7b296b42c0fccdf7`,
`image_id sha256:555b939841d9fe1f86cc623106d669f06b2ecde11323982b2af908c5546ae696`.
Do not add a long-lived product JWT to an agent profile without a scoped-token
design.

## Squads (2026-11-17)

| Squad | Leader | Members |
|---|---|---|
| Leadership — Żar i Szlif | CEO | 6 |
| Engineering — CTO | CTO | 5 |
| Growth & Lifecycle — CMO | CMO | 3 |
| Harness — CHO | CHO | 2 |
| Mascots — CPO | CPO | 2 |

A squad routes a mention to its leader; it is not an enforced `reportsTo`
hierarchy. The leader must create sub-issues explicitly. Cross-squad acceptance
(e.g. CMO/UI QA accepting mascot work) is a task assignment, not a squad
membership.

## Workflow (2026-11-17)

Five workflows now exist across six projects; the 2026-11-13 "one Default
workflow" statement is obsolete.

| Workflow | Covers | Agent-handled steps |
|---|---|---|
| `Default` (`e33c6c4a…`, `is_default`) | Agent Knowledge Benchmark, Żar i Szlif — Product (both report `workflow_id: null`) | `in_review → CTO → done` |
| `Harness — CHO intake, HE build, CTO review` (`56f18e93…`) | Żar i Szlif — Harness | `in_review → CTO → awaiting_deployment`; `awaiting_deployment → COO → production_qa`; `production_qa → UI QA → done` |
| `Growth — Parent Orchestration` (`c6ff58d7…`) | Żar i Szlif — Growth & Lifecycle | `in_review → CEO → done` |
| `Isolation — CHO scope, authorized fix, independent CTO` (`6f4f19f7…`) | Żar i Szlif — Runtime Security & Isolation | `in_progress → Harness Engineer → in_review`; `in_review → CTO → blocked` |
| `Mascot Factory — Review → Release → Prod` (`4c2161c4…`) | Żar i Szlif — Mascot Factory | `in_review → CTO`, no next status |

Every workflow has native statuses `backlog`, `todo`, `in_progress`, `in_review`,
`blocked`, `done`, `cancelled`; the Harness workflow adds
`awaiting_deployment` and `production_qa`. When CTO authored the change, an
independent CHO review is required; this stays an instruction-level rule because
Multica supports one handler per status.

### Done gate — NOT installed

The independent Done gate described in earlier revisions of this file does not
exist on `main` or on the host. Verified 2026-11-17:

- `git ls-tree -r --name-only origin/main -- ops/` → only
  `ops/release-lanes.json`, `ops/systemd/product-native-promotion.service`,
  `ops/systemd/product-native-promotion.timer`. No `ops/multica-done-gate/`.
- No `multica_done_gate.py` under `/usr/local/libexec/`; no `done-gate` systemd
  unit in `/etc/systemd/system/`.
- The only host copy is `/tmp/multica_done_gate.py` (7.7 kB, 2026-11-13, owned by
  an unprivileged account) — a scratch file, not an installed control.
- PR #103 `ops: independent Done gate, edge watchdog and verified workspace
  record` is **CLOSED, unmerged** (`closedAt 2026-11-13T19:17:35Z`), head
  `4d9f473783683ceaeccc461e2c76354a2d08b9c2`; branch `feat/multica-done-gate`
  still points at that commit.
- Tracking issue **ZARI-202 is `blocked`**.

Consequence: nothing auto-reverts a self-approved producer or a `Release …`
issue closed without promotion evidence. Done discipline is currently
instruction-level plus reviewer enforcement. The previously documented
`sudo python3 /usr/local/libexec/multica_done_gate.py --self-test` cannot run
and has been removed from the verification commands below. Re-landing the gate
requires a real review of `4d9f4737`, per the rules in `docs/RELEASE-POLICY.md`.

## GitHub delivery (2026-11-17)

- Repositories: `miloszspyrka-code/zar-i-szlif` (product) and
  `miloszspyrka-code/harness-zar-i-szlif` (infrastructure).
- Credentials: root broker `multica-git-credential-broker.py` over a unix
  socket, `SO_PEERCRED` + daemon process-tree check, roles `implementer`,
  `reviewer`, `release` in `/etc/multica-git-credential/agent-roles.json`.
  Tokens are installation tokens for App 5398752, scoped to exactly those two
  repositories, TTL about one hour, never printed by the broker.
- **Broker E2E proven 2026-11-13**: Harness Engineer (`c1c8b457…`,
  `implementer`) pushed `chore/credential-broker-e2e-20261113` and opened PR
  #102; broker log shows three `credential … role=implementer
  repo=harness-zar-i-szlif` grants for that agent. Re-read 2026-11-17: PR #102
  head still `5e2f3771cc708212ea21315d21594313d7a8f973` (PR itself is now
  CLOSED unmerged; the head match is the evidence). Original evidence: ZARI-201.

### Branch protection and rulesets — 403s have different causes

Verified 2026-11-17 with the workspace App token (App 5398752):

| Call | Response |
|---|---|
| `GET /repos/{owner}/{repo}/branches/main/protection` | `403 {"message":"Resource not accessible by integration"}` |
| `GET /repos/{owner}/{repo}/rulesets` | `403 {"message":"Upgrade to GitHub Pro or make this repository public to enable this feature."}` |
| `GET /repos/{owner}/{repo}` | `private: true`, `visibility: private`, `permissions: {admin: false, maintain: false, pull: false, push: false, triage: false}` |

So the **branch-protection** 403 is an App-permission response and does **not**
by itself establish the plan as the cause; the **rulesets** 403 states the plan
limitation explicitly. What is verified either way: no server-side protection is
in force, and this identity cannot administer the repository. Compensating
controls: role-scoped broker, native exact-SHA gate before deploy,
`ci-approved` advanced only by the controller, pre-push hook. They are controls,
not a substitute for real rulesets: an implementer token still carries
`contents:write` for both repositories.

## Known gaps (open, 2026-11-17)

1. **CI cannot start — billing.** Both required checks
   (`validate-release-lanes` from `release-lanes-policy.yml`,
   `validate-paperclip-mcp` from `paperclip-mcp-ci.yml`; both run on every PR
   with no path filter) are created and then completed/failure *without a job*.
   Current readback: at `main` head `75f7086` check-run `134018273581`
   (`validate-release-lanes`) and at PR #104 head `af9e1fe` check-runs
   `132111108216`/`132111108221`, all carrying the annotation
   *"The job was not started because recent account payments have failed or your
   spending limit needs to be increased."* No PR in `harness-zar-i-szlif` gets
   CI until the account billing state is fixed; local runs are a substitute, not
   the required check.
2. **No server-side branch protection** — see the 403 table above; unblock with
   GitHub Pro or public repositories, then require PR, review, checks and
   restrict `ci-approved`.
3. **No automated Done gate** — see "Done gate — NOT installed" (PR #103,
   `4d9f4737`, ZARI-202 `blocked`).
4. **Per-agent inline MCP servers are unreadable** — `mcp_config` is redacted for
   every agent, so a server registered inline instead of through the workspace
   library cannot be verified from the API. Either move such servers into the
   workspace library or publish the rendered profile as evidence.
5. **Backlog counts** — predicate stated so the number is checkable. Enumerating
   every issue on 2026-11-17 (242 total: 158 `done`, 55 `cancelled`, 20
   `blocked`, 5 `in_review`, 2 `in_progress`, 2 `backlog`):
   - `in_review` = **5** — ZARI-204 (2026-11-13T21:13:54Z), ZARI-229, ZARI-236,
     ZARI-237, ZARI-242 (2026-11-16). The 19 MIGRATION-era issues and
     ZARI-29/33/58/138 that made up the earlier 23 are no longer `in_review`.
   - `blocked` = **20**, of which **0** have no assignee (every one is assigned
     to an agent, a squad, or the workspace owner).
   - `[legacy KOMAA-…]`-prefixed issues = **13**, all `cancelled`; none remain
     `blocked`. One further issue carries a KOMAA title without the `legacy`
     prefix — ZARI-95 `[KOMAA-1538]`, `blocked`, assigned to CHO.
   Triage these explicitly; do not mass-close.
6. **Public edge has no installed watchdog** (2026-11-13 incident; not
   re-tested 2026-11-17). `coolify-caddy` stayed down 33 minutes after a Docker
   daemon restart because a referenced network was missing; it was restored
   manually. The draft watchdog lives only in the closed PR #103 (head
   `4d9f4737`) and is not installed: it needs a consecutive-failure threshold and
   an alert channel before it may restart the public edge.
7. **Duplicate dispatch on status transitions** (2026-11-13, not re-tested) —
   moving an issue to `in_review` while a run is active queues a second run;
   concurrency 2 makes both start (observed on ZARI-200).
8. **Run status lags issue status** (2026-11-13, not re-tested) — a run can stay
   `running` after its result comment is posted (observed on ZARI-201). Do not
   treat `running` alone as an execution failure.
9. **No automatic retry** (2026-11-13, not re-tested) — six runs failed on the
   old `gpt-6-luna` selection and nothing retried them; `max_attempts=2` is not
   applied by the runtime.
10. **Mautic/Emailens** are transport-green but data-empty (2026-11-13, not
    re-tested: 0 campaigns, 0 segments).
11. **Mascot image generation** remains blocked (2026-11-13, not re-tested):
    hosted image tool account on `free`, no OpenAI/fal key, no local diffusion
    weights.

## Live edge (2026-11-17)

| Probe | Result |
|---|---|
| `GET https://panel.zariszlif.pl/__release.json` | 200, `{"commit":"e5880d53e9bb9f0dc1b201ec7b296b42c0fccdf7","source":"zar-i-szlif/main"}` |
| `GET https://panel.zariszlif.pl/healthz` | 200 |
| `GET https://mcp.zariszlif.pl/health` | 200, `{"ok":true,"name":"zar-i-szlif-product-host-mcp","version":"0.1.1","environment":"staging"}` |

## Verification commands

```bash
# Runtime, agents, MCP library and per-agent assignment
multica runtime list --output json
multica agent list --output json
multica workspace mcp list --output json
multica agent mcp list <agent-id> --output json
# Agents, squads, workflows, projects
multica squad list --output json
multica workflow list --output json
multica project list --output json
# Backlog predicate (gap 5)
multica issue list --status in_review --output json
multica issue list --status blocked --output json
# Live edge
curl -s https://panel.zariszlif.pl/__release.json
curl -s -o /dev/null -w '%{http_code}\n' https://panel.zariszlif.pl/healthz
curl -s https://mcp.zariszlif.pl/health
sudo python3 /usr/local/libexec/mcp_host_live_canary.py && cat /var/lib/multica-canary/mcp-host.json
# GitHub state (gaps 1, 2)
gh api repos/miloszspyrka-code/harness-zar-i-szlif/branches/main/protection
gh api repos/miloszspyrka-code/harness-zar-i-szlif/rulesets
gh api repos/miloszspyrka-code/harness-zar-i-szlif/commits/$(git rev-parse origin/main)/check-runs
# Done gate absence (gap 3) — absence is the expected result
git ls-tree -r --name-only origin/main -- ops/
ls /usr/local/libexec/multica_done_gate.py
# Broker
journalctl -u multica-git-credential-broker -n 20
```
