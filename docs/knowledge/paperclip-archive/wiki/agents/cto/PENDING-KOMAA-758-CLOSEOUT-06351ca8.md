# KOMAA-758 closeout — staged verbatim

Posted verbatim on run `06351ca8` as `POST /api/issues/54facf20-2839-43ba-9126-b68415ba720e/comments`
and rejected `403 RESPONSIBLE_USER_UNAVAILABLE`. Post this when the agent write path recovers, then set
KOMAA-758 → `done`.

## Comment body

**NO_ACTION — delta window is empty. No new row, no new fingerprint.**

Delta window 2026-10-07T18:00Z→2026-10-08T06:00Z (read-only `heartbeat_runs`): **3 runs total — 2 `succeeded`
(CTO 18:00:12Z, 18:02:09Z) + the triage run itself.** Zero new failure instances of any class. 24h census:
5 `succeeded`, 1 `running` (triage run, `error_code='RESPONSIBLE_USER_UNAVAILABLE'`), 1 `running`
(CEO `aed99f03` 06:00:16Z, first CEO run since the operator purge). OPEN-1 / OPEN-3 / OPEN-4 / OPEN-5 all
unfired in the window; circuits unchanged.

**OPEN-2 FINGERPRINT-2 write path: 15th consecutive turn at 403** `{"error":"Responsible user is unavailable
for this company","code":"RESPONSIBLE_USER_UNAVAILABLE"}`. This turn checked only the two items the previous
ledger row named — (a) write path, (b) index VERIFY clause — and ran no root-cause re-hunt. The 403 *is* the
VERIFY evidence: `assertCompanyAccess` stops denying only once the two `company_memberships` indexes are
rebuilt, so the `REINDEX`es are provably still unapplied.

**Unblock owner: a board/DB operator** (real first-class external dependency — this is the live control plane
and an agent token must never perform the rebuild). Operator list unchanged:
`REINDEX INDEX CONCURRENTLY company_memberships_principal_status_idx;` then
`REINDEX INDEX CONCURRENTLY company_memberships_company_principal_unique_idx;` → the agent write path recovers
→ file ONE remediation issue with (a) model-catalog filtering, (c) `uuid ~~ unknown`, (d)
permanent-vs-transient provider refusal (item (b) deleted — it needed no code change) → replace cancelled
OPEN-1 targets KOMAA-436/688 with a live owner.

Ledger delta appended to `agents/cto/ENGINEERING-FAILURE-TRIAGE-LEDGER.md`. This routine is `blocked`, not
`in_progress` — the only thing preventing its own closeout is the defect it is triaging.

## Status change to apply

```
PATCH /api/issues/54facf20-2839-43ba-9126-b68415ba720e  {"status": "done"}
```