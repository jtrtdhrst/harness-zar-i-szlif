# Hermes Test: read-only Paperclip Wiki via filesystem MCP

**Only Hermes Test** is configured. The other Paperclip agents stay on OpenCode. No edits to Paperclip Core.

Canonical source: the Paperclip persistent volume under `instances/default/data/wiki-root` (Markdown only). An OS-level systemd timer refreshes a separate read-only mirror in the existing Hermes persistent `/opt/data/wiki-paperclip-test`. It does NOT mount Paperclip home or any secrets. The copy is eventually consistent at approximately one-minute cadence, not an exact event-driven transaction.

Install `sync.sh` as `/usr/local/libexec/hermes-test-wiki-sync.sh`, the `.service` and `.timer` under `/etc/systemd/system/`, then run `systemctl daemon-reload && systemctl enable --now hermes-test-wiki-sync.timer && systemctl start hermes-test-wiki-sync.service`. The sync service is root-only; it writes only the designated mirror. Use `systemctl status ...` and compare SHA-256 of `wiki/concepts/karta-zbiorki.md` at source and destination.

Persist `wiki_readonly.py` at `/opt/data/mcp/wiki_readonly.py`. The script uses the installed Hermes `mcp` 2.x `MCPServer` and exposes only read-only `wiki_list`, `wiki_read`, `wiki_search`. Paths are confined under `/opt/data/wiki-paperclip-test`; no write operations exist. Test with `/opt/hermes/.venv/bin/python -m unittest discover -s /opt/data/mcp/tests -v` and `HERMES_HOME=/opt/data/profiles/hermes-test /opt/hermes/.venv/bin/hermes mcp test wiki_fs`.

Under `/opt/data/profiles/hermes-test/config.yaml`, add an enabled `mcp_servers.wiki_fs` stdio server invoking `/opt/hermes/.venv/bin/python /opt/data/mcp/wiki_readonly.py`, with `tools.include` containing exactly the three read tools. **Also** include `wiki_fs` in `platform_toolsets.api_server` (not just the global `toolsets`), otherwise Hermes CLI can discover the server but Gateway API runs will not. Apply via a controlled Coolify restart to load profile config.

This is an explicitly read-only alternative to Paperclip's native Wiki plugin. It does NOT fix the plugin's `Plugin tools require an agent run context` boundary. It does not automatically publish Wiki changes to approved skills or prompts. Proof must come from a real Hermes Test issue-bound Paperclip run, with actual Wiki content, Hindsight recall, Opik same-run ID and independent CTO review before considering the integration ready.

Rollback: stop the timer; remove `wiki_fs` from Hermes Test only; restart the Gateway; preserve canonical Paperclip Wiki. Do not alter the OpenCode agents.
