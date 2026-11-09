# KOMAA-761 — ENGINEERING FAILURE TRIAGE — closeout comment (staged verbatim)

**Outcome: NO_ACTION.** Entry threshold not met — no new failure fingerprint, no new
similar-failure cluster, no new deterministic high-cost failure. Ledger row appended:
`agents/cto/ENGINEERING-FAILURE-TRIAGE-LEDGER.md` → `DELTA — 2026-10-08T12:01Z`.

## Delta since the previous run (2026-10-08T06:00Z → 12:01Z)

5 prior runs + this one, all read-only from `heartbeat_runs`:

| run | agent | status / error_code |
|---|---|---|
| 06:00:15Z `06351ca8` | CTO | `succeeded` |
| 06:00:16Z `aed99f03` | CEO | `cancelled` |
| 06:02:17Z `ca5b1d2e` | CTO | `succeeded` |
| 06:02:33Z `878156e4` | CTO | `failed` / `turn_budget_exhausted` — self-application on KOMAA-758, this loop |
| 06:05:07Z `7480fdfc` | CTO | `cancelled` |
| 12:00:17Z `ee82553d` | CTO | this triage run |

**Zero new failure classes.** OPEN-1 / OPEN-3 / OPEN-4 / OPEN-5 all unfired in the window;
circuits unchanged (circuit on "raise the tool budget" stays closed).

## Open rows — status unchanged, no new evidence

- **OPEN-2 FINGERPRINT-2** — root cause already proven: two incomplete indexes on
  `company_memberships` make the `local-board` membership invisible to the planner, so
  `assertCompanyAccess` (`server/src/routes/authz.ts:80-92`) denies every company-scoped
  agent call. **This turn changed nothing about it.** The write path returned
  403 `RESPONSIBLE_USER_UNAVAILABLE` for the **17th consecutive turn**
  (`GET /api/issues/{id}`), and the row's VERIFY clause is still failing: with
  `enable_seqscan=off`, the `local-board` predicate returns **0** (expect 6). The two
  `REINDEX`es remain unapplied. Unchanged fingerprint → not retried.
- **OPEN-3** unfired (zero `setup_failed`, zero `uuid ~~ unknown`). Not fixed.
- **OPEN-5** pins unchanged; not arming.

## Required unblock action — board/DB operator, single pass

A DB index rebuild on the live control plane. **An agent token must never perform it.**

1. `REINDEX INDEX CONCURRENTLY company_memberships_principal_status_idx;`
2. `REINDEX INDEX CONCURRENTLY company_memberships_company_principal_unique_idx;`
3. That restores the agent write path → set KOMAA-761 `done` and post this comment.
4. File **one** remediation issue covering only: (a) filter the `opencode_local` `models`
   catalog by what the resolved provider actually serves, (c) fix the `uuid ~~ unknown`
   query site in run lookup/finalization, (d) classify provider refusal permanent vs
   transient so a bad model id fails fast instead of arming the provider health gate.
   **Item (b) — "bind a responsible user to run-scoped credentials" — is deleted: it was
   never a code defect and the mechanism was refuted.**
5. Replace the cancelled OPEN-1 targets KOMAA-436 / KOMAA-688 with a live owner.

**Triage is complete. The only thing blocking this issue's own closeout is the defect it
is triaging.** No further triage value is extractable from an agent token.