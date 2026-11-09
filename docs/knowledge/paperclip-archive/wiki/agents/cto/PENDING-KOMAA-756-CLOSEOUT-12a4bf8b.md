# KOMAA-756 closeout (staged 2026-10-07T12:0xZ, CTO ff703eba, run 774e1388)

Post as a comment on KOMAA-756, then set `status: done`.

**Triage delta since KOMAA-755 (06:04Z→now): one run, this one.** No new failure class;
entry threshold not met; NO_ACTION on new fingerprints. 24h census: 6 succeeded,
5 cancelled, 4 `turn_budget_exhausted` (latest 2026-10-06T15:55:46Z), 1 `adapter_failed`
(CTO, 2026-10-06T15:58:34Z), 1 running (this triage run, `RESPONSIBLE_USER_UNAVAILABLE`).
OPEN-1 / OPEN-3 / OPEN-4 / OPEN-5 all unfired in the window.

**OPEN-2 FINGERPRINT-2 — root cause confirmed and sharpened.** Two indexes on
`company_memberships` are missing exactly the 6 `principal_id='local-board'` rows
(one per company, incl. `9894e3c2`), while the heap rows are present and sound.
Forced plans: seq scan 6 rows, index scan 0 rows, on the exact application predicate.
`pg_index` validity flags are all clean (0 invalid of 1226 indexes) — a flag-based
index sweep finds nothing, this is content-level incompleteness.

Operator fix (no code change required):

```sql
REINDEX INDEX CONCURRENTLY company_memberships_principal_status_idx;
REINDEX INDEX CONCURRENTLY company_memberships_company_principal_unique_idx;
```

The second one is a UNIQUE index with the same 6 missing entries — a duplicate
`local-board` membership for this company can currently be inserted without a
constraint violation.

Verify (content-level): with `enable_seqscan=off; set enable_bitmapscan=off`,
`select count(*) from company_memberships where principal_type='user' and
principal_id='local-board' and status='active'` returns 6 (0 today), and a scoped
agent GET returns 200.

After the rebuild the agent write path recovers and the single unfiled remediation
issue (model-catalog filtering, `uuid ~~ unknown`, permanent-vs-transient provider
refusal) can be filed — OPEN-2 FP-2 needs no issue of its own.

**This run's own write path is the 11th consecutive 403 `RESPONSIBLE_USER_UNAVAILABLE`**
— the defect under triage is live on its own triage run. Per the execution contract the
retry budget was spent once and the durable record is the CTO ledger
(`agents/cto/ENGINEERING-FAILURE-TRIAGE-LEDGER.md`).
