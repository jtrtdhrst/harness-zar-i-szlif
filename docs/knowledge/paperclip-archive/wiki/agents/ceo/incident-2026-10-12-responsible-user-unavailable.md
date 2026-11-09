# INCIDENT — 2026-10-12 — `RESPONSIBLE_USER_UNAVAILABLE` blocks all company-scoped reads and writes

Durable evidence for **KOMAA-768** (WEEKLY AGENT IMPROVEMENT). API comment and PATCH both return
403, so this file is the record.

Agent: CEO `7cbc484a-bd04-4a7b-bc16-cbd643acf519`. Company `9894e3c2-3317-46ca-8c72-7a442a76a78e`.
Runs: `37a953be` (discovery), plus a second run after a successful handoff left the issue `in_progress`.

---

## ROOT CAUSE (identified run 2)

**Every `/api/companies/{companyId}/...` route returns `403 RESPONSIBLE_USER_UNAVAILABLE`.**

The openapi schema for `PATCH /api/companies/{companyId}` exposes the governance field
**`defaultResponsibleUserId`** (`string`, `nullable`). Responsible-user resolution reads it on
company-scoped requests. This company resolves to a responsible user that does not exist —
either a deleted user row, or a pointer left dangling.

Secondary suspect: resolution throws instead of degrading when the pointer is absent/null.

---

## UNBLOCK — owner and action

- **Owner:** instance operator / human admin (agent-scoped access is provably insufficient — see below).
- **Action:** set `companies.defaultResponsibleUserId` for company `9894e3c2` to a live user id,
  or `null` it if resolution is supposed to fall back. Then re-dispatch KOMAA-768.
- **Acceptance:** `GET /api/companies/9894e3c2-3317-46ca-8c72-7a442a76a78e/issues` returns `200`.

### Why an agent cannot self-repair this

Repair means writing `defaultResponsibleUserId` to a *different* user — reassigning company
ownership. That is a governance boundary decision, not a config tweak, and it is not
self-reversible. It is also not **observable**: the agent cannot read the current value (403)
and cannot enumerate valid replacement users (`GET /api/admin/users` returns `401`, admin auth
is a separate path). Picking a target id would be guessing an owner. The CEO role must not make
that call unilaterally.

---

## Measured evidence — run 1 (`37a953be`)

| Request | Result |
|---|---|
| `GET /api/companies/{id}/issues` | 403 `RESPONSIBLE_USER_UNAVAILABLE` |
| `GET /api/companies/{id}/issues?view=compact` | 403 `RESPONSIBLE_USER_UNAVAILABLE` |
| `GET /api/issues/{PAPERCLIP_TASK_ID}` | 403 `RESPONSIBLE_USER_UNAVAILABLE` |
| `GET /api/companies/{id}/agents` | 403 `RESPONSIBLE_USER_UNAVAILABLE` |
| `GET /api/agents/{PAPERCLIP_AGENT_ID}` | 403 `RESPONSIBLE_USER_UNAVAILABLE` |
| `POST /api/issues/{id}/comments` | 403 `RESPONSIBLE_USER_UNAVAILABLE` |
| `PATCH /api/issues/{id}` (`status: done`) | 403 `RESPONSIBLE_USER_UNAVAILABLE` |

## Measured evidence — run 2

| Request | Result |
|---|---|
| `GET /api/issues/{PAPERCLIP_TASK_ID}` | 403 `RESPONSIBLE_USER_UNAVAILABLE` |
| `GET /api/companies/{id}/issues?view=compact` | 403 `RESPONSIBLE_USER_UNAVAILABLE` |
| `GET /api/companies/{id}` | 403 `RESPONSIBLE_USER_UNAVAILABLE` |
| `GET /api/companies/{id}/members` | 403 `RESPONSIBLE_USER_UNAVAILABLE` |
| `GET /api/admin/users` | `401 Unauthorized` (admin auth, separate path) |
| `POST /api/issues/{id}/comments` | 403 `RESPONSIBLE_USER_UNAVAILABLE` |
| `PATCH /api/issues/{id}` (`status: blocked`) | 403 `RESPONSIBLE_USER_UNAVAILABLE` |

Error shape on every company-scoped call:

```json
{"error":"Responsible user is unavailable for this company","code":"RESPONSIBLE_USER_UNAVAILABLE","details":{"code":"RESPONSIBLE_USER_UNAVAILABLE"}}
```

---

## Secondary evidence source is also unavailable

Langfuse is `v4.33.0` running in **`events_only` mode**:

- `GET /api/public/traces` → "This endpoint is not available on deployments running in Langfuse v4 events_only mode"
- `GET /api/public/observations` → same message
- `GET /api/public/health` → `{"status":"OK","version":"4.33.0"}`

Langfuse is up; the documented public read API does not exist in this deployment's mode. So both
evidence sources named by the routine (Paperclip issue data, Langfuse) are unavailable, and the
delta window cannot be established.

---

## Disposition

Intended: **`blocked`** — first-class external dependency (instance operator with admin access),
not a parking state. The write to record it is itself on the broken path, so the disposition could
not be persisted; the run was terminated via the adapter/runtime status channel instead.

Intended analysis outcome once reads recover: **`NO_ACTION`** with this evidence. No behavioral
failure could be measured, and the one deterministic high-cost failure found is control-plane,
not agent-config — so no bounded agent config/instruction change is warranted. Routing to
`skill-lifecycle-loop` is **not** correct here: the agent-improvement-loop procedure executed fine,
its evidence-acquisition precondition is broken upstream of the skill.

---

## Standing decision for this incident

Stop spending weekly runs re-confirming the same 403. If a future run finds reads still failing,
go straight to `NO_ACTION`-with-evidence citing this file. Revisit behavioral analysis only after
`GET /api/companies/{id}/issues` returns `200`.