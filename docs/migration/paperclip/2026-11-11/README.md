# Paperclip → Multica: bounded source metadata archive (2026-11-11)

This is a **read-only Paperclip extraction** into an isolated review branch. It is NOT a 1:1 Multica task import, not a completed migration of comments, PRs, execution history or all dependency edges, and not evidence that old tasks should be automatically rerun.

- Source records: **1260** issues, unique IDs: **1260**; counts: cancelled 437, done 808, blocked 10, in_review 3, in_progress 2.
- Source projects: **15**, roles: **14**; unresolved/nonterminal issue records: **15**.
- Source issue metadata split across two JSONL files and context (project/agent mapping, first-class blockers for nonterminal issues) in `context.json`.
- No descriptions, chat/comment bodies, secrets, credentials, account or human user IDs, runtime environment values or private URLs were copied. Issue titles have emails and HTTP(S) URLs redacted.
- Only exact source records are stored here; importing these into a new project would invent execution ownership and might restart stopped source work. Any selective migration must preserve source link, parent and blocker relations, and the source Paperclip remains read-only.
- Do not merge until an independent reviewer has verified source counts, duplicate safety and redaction. This archive lives under `docs/migration/`, outside the live `multica-mcp/**` deployment watch path.
