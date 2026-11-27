# Paperclip → Multica: bounded source metadata archive (2026-11-11)

This is a **filtered historical Paperclip extraction**; it is not a new source readback. It is NOT a 1:1 Multica task import, not a completed migration of comments, PRs, execution history or all dependency edges, and not evidence that old tasks should be automatically rerun.

- Retained source records: **1239** issues, unique IDs: **1239**; counts: cancelled 422, done 802, blocked 10, in_review 3, in_progress 2.
- Retained source projects: **14**, roles: **14**; unresolved/nonterminal issue records: **15**.
- Source issue metadata split across two JSONL files and context (project/agent mapping, first-class blockers for nonterminal issues) in `context.json`.
- No descriptions, chat/comment bodies, secrets, credentials, account or human user IDs, runtime environment values or private URLs were copied. Issue titles have emails and HTTP(S) URLs redacted.
- Retained records are filtered to the current repository scope; parent links to excluded records have been removed. Original source records remain in previous Git history; importing these into a new project would invent execution ownership and might restart stopped source work. Any selective migration must preserve source link, parent and blocker relations, and the source Paperclip remains read-only.
- Do not merge until an independent reviewer has verified retained record counts, duplicate safety and redaction. This archive lives under `docs/migration/`, outside the live `multica-mcp/**` deployment watch path.
