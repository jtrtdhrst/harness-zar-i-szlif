# Hermes Test: read-only Paperclip Wiki via filesystem MCP

**Only Hermes Test** is configured. The other Paperclip agents stay on OpenCode. No edits to Paperclip Core.

Canonical source: the Paperclip persistent volume under `instances/default/data/wiki-root` (Markdown only). An OS-level systemd timer refreshes a separate read-only mirror in the existing Hermes persistent `/opt/data/wiki-paperclip-test`. It does NOT mount Paperclip home or any secrets. The copy is eventually consistent at approximately one-minute cadence, not an exact event-driven transaction.

Install `sync.sh` as `/usr/local/libexec/hermes-test-wiki-sync.sh`, the `.service` and `.timer` under `/etc/systemd/system/`, then run `systemctl daemon-reload && systemctl enable --now hermes-test-wiki-sync.timer && systemctl start hermes-test-wiki-sync.service`. The sync service is root-only; it writes only the designated mirror. Use `systemctl status ...` and compare SHA-256 of `wiki/concepts/karta-zbiorki.md` at source and destination.

Persist `wiki_readonly.py` at `/opt/data/mcp/wiki_readonly.py`. The script uses the installed Hermes `mcp` 2.x `MCPServer` and exposes only read-only `wiki_list`, `wiki_read`, `wiki_search`. Paths are confined under `/opt/data/wiki-paperclip-test`; no write operations exist. Test with `/opt/hermes/.venv/bin/python -m unittest discover -s /opt/data/mcp/tests -v` and `HERMES_HOME=/opt/data/profiles/hermes-test /opt/hermes/.venv/bin/hermes mcp test wiki_fs`.

Under `/opt/data/profiles/hermes-test/config.yaml`, add an enabled `mcp_servers.wiki_fs` stdio server invoking `/opt/hermes/.venv/bin/python /opt/data/mcp/wiki_readonly.py`, with `tools.include` containing exactly the three read tools. **Also** include `wiki_fs` in `platform_toolsets.api_server` (not just the global `toolsets`), otherwise Hermes CLI can discover the server but Gateway API runs will not. Apply via a controlled Coolify restart to load profile config.

This is an explicitly read-only alternative to Paperclip's native Wiki plugin. It does NOT fix the plugin's `Plugin tools require an agent run context` boundary. It does not automatically publish Wiki changes to approved skills or prompts. Proof must come from a real Hermes Test issue-bound Paperclip run, with actual Wiki content, Hindsight recall, Opik same-run ID and independent CTO review before considering the integration ready.

Rollback: stop the timer; remove `wiki_fs` from Hermes Test only; restart the Gateway; preserve canonical Paperclip Wiki. Do not alter the OpenCode agents.

## Hermes Test API Gateway toolset correction

Profile configuration must include all three toolsets explicitly for the API server:

```yaml
platform_toolsets:
  api_server:
    - hermes-cli
    - pc
    - wiki_fs
```

The `pc` MCP connection should whitelist only the two verified published-skill read tools (`papercliplistskills`, `paperclipgetskillfile`) in this pilot. The legacy native Wiki plugin entries return `Plugin tools require an agent run context` with reusable named gateway credentials; remove them from the pilot's `pc.tools.include` to prevent model misrouting. Use the separate `wiki_fs` tools for canonical Wiki reads.

The initial real Paperclip canary KOMAA-1518, run `36428ebb-3a14-45e2-b174-5c1ef8ec09b8`, succeeded in Wiki file read, published Skills, Hindsight recall and Opik correlation. Opik trace `01a19c9e-e5b3-7eac-80d5-22c407ff275e` has `metadata.task_id=paperclip:run:36428ebb-3a14-45e2-b174-5c1ef8ec09b8`. The issue's independent CTO review is stuck behind a stale cancelled-executor recovery marker, tracked separately; do not claim review approved.

Runbooks and tests are intentionally scoped to Hermes Test; do not change or redeploy the 15 OpenCode agents.
