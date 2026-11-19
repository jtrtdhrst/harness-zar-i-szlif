# KOMAA-757 — staged closeout (post verbatim when a write path exists)

**ENTRY THRESHOLD: NOT MET → NO_ACTION.** No new row entered; no new remediation issue filed.

**Delta window** 2026-10-07T12:00Z → 18:00Z: **3 runs — 2 `succeeded` (CTO 12:00:10Z, 12:05:18Z) + this triage run. Zero new failures of any code.** 24h census: 5 `succeeded`, 1 `running` (this run). OPEN-1 / OPEN-3 / OPEN-4 / OPEN-5 all unfired in the window; circuits unchanged.

**One new decision-relevant fact (this turn's only new evidence):** the index damage is **confined to `company_memberships`** — it is not a class-wide restore artefact, so no `REINDEX DATABASE` and no other-table audit is needed.

- `principal_permission_grants` — the only other table with `principal_type` / `principal_id` — has **244 heap rows, all 244 visible** through its own unique index on `(company_id, principal_type, principal_key…)` under a forced index-only plan, including **all 103 `local-board` grant rows**. Complete.
- `company_memberships`: still 25 of 31 rows index-visible; the 6 invisible rows are exactly the `local-board` memberships.
- **Consequence:** rebuilding the two named indexes is a **complete** fix, and authorization will not then fail on a missing grant — `local-board`'s 103 permission grants are all indexed.
- Both index definitions re-confirmed, so the prescribed SQL is valid as written: `company_memberships_principal_status_idx` btree `(principal_type, principal_id, status)` and `company_memberships_company_principal_unique_idx` btree `(company_id, principal_type, principal_id)` — plain btree, non-partitioned, so `CONCURRENTLY` applies directly.

**OPEN-2 FINGERPRINT-2 VERIFY clause re-measured, unchanged:** forced index plan for `principal_type='user' AND principal_id='local-board' AND status='active'` still returns **0** (expect 6) → the REINDEXes have **not** been applied. Unchanged fingerprint; not retried, not re-hunted.

**Write path: 13th consecutive turn at 403 `RESPONSIBLE_USER_UNAVAILABLE`.** This turn attempted `GET /api/issues/{id}` and `PATCH /api/issues/{id}` once each and then stopped, per the 2-failure rule; the runtime status channel plus `agents/cto/ENGINEERING-FAILURE-TRIAGE-LEDGER.md` are the sanctioned fallback. KOMAA-757 reads `in_progress` although triage is finished — the blocker is the defect under triage, not remaining analysis. **Blocked, with a named unblock owner: a board operator / DB operator.** This is a genuine first-class external dependency (a DB index rebuild the agent must never perform, because it is the live control plane), not "more analysis available".

**Operator list (unchanged, and now narrower):**
1. `REINDEX INDEX CONCURRENTLY company_memberships_principal_status_idx;` then `REINDEX INDEX CONCURRENTLY company_memberships_company_principal_unique_idx;`
2. That restores the agent write path → set KOMAA-757 to `done` and post this file.
3. File **one** remediation issue carrying only: (a) filter the `opencode_local` `models` catalog by what the resolved provider will serve, (c) fix the `uuid ~~ unknown` query site, (d) classify provider refusal permanent vs transient so a bad model id fails fast instead of arming the health gate. **Item (b) is deleted — the responsible-user denial needed no code change.**
4. Replace the cancelled OPEN-1 targets KOMAA-436 / KOMAA-688 with a live owner.

Next triage wake: do **not** re-run this census or the responsible-user root-cause hunt. Only check (a) whether the write path recovered and (b) the index VERIFY clause.