# Hermes Gateway — scoped read-only Paperclip Wiki MCP

**Current production contract (2026-11-03): 14 real Hermes profiles; the retired `hermes-test` actor is NOT configured or supported.**

## Source, ownership and synchronization

Paperclip Markdown under `instances/default/data/wiki-root` is authoritative. The host mirrors Markdown only to the existing, historically named persistent path `/opt/data/wiki-paperclip-test`, using [`sync.sh`](sync.sh) with its existing `rsync` allowlist and read-only destination permissions. The snapshot is eventually consistent on a one-minute timer; it is **not** a live transactional Paperclip MCP read.

Production Linux service templates are tracked at [`systemd/hermes-paperclip-wiki-sync.service`](systemd/hermes-paperclip-wiki-sync.service) and [`.timer`](systemd/hermes-paperclip-wiki-sync.timer); the installed script path is `/usr/local/libexec/hermes-paperclip-wiki-sync.sh`. As verified on the VPS, `hermes-paperclip-wiki-sync.timer` is enabled and active. The obsolete `hermes-test-readiness` and `hermes-test-wiki-sync` units are disabled on the host and deleted from current repository paths; their history remains in Git.

Do **not** enable a second timer or change production mounts when pulling this repository. CHO must review release and the existing systemd configuration before any deployment.

## Agent profile isolation

The only current Wiki MCP server source is [`wiki_scoped.py`](wiki_scoped.py), installed in the Hermes persistent data volume at `/opt/data/mcp/wiki_scoped.py`. Each of the 14 real profiles binds its **own** read-only stdio server, e.g.:

```yaml
mcp_servers:
  wiki_fs:
    command: /opt/hermes/.venv/bin/python
    args:
      - /opt/data/mcp/wiki_scoped.py
      - --profile
      - cho
    tools:
      include: [wiki_list, wiki_read, wiki_search]
platform_toolsets:
  api_server:
    - wiki_fs
```

This YAML is illustrative; preserve any other explicitly approved `platform_toolsets.api_server` values rather than replacing the entire list. The scoped code only allows own `wiki/agents/<profile>/` pages and approved shared locations, rejects traversal/symlinks, exposes only `wiki_list`, `wiki_read` and `wiki_search`, and never writes Paperclip or Hermes state.

## Validation and explicit limitations

- Production empirical 2026-11-03: `hermes -p <real-role> mcp test wiki_fs` **14/14 PASS**, repeated after a Coolify Hermes restart. Evidence `/opt/hermes-gateway-ops/e2e-evidence/real-14-profile-wiki-mcp.json`.
- Real scope-denial test: Engineer requesting `wiki/agents/engineer/` returned one page; CPO requesting the identical prefix returned zero pages. Hermes-native Opik traces prove actual tool spans.
- The live scoped tests run **inside Hermes with its MCP package and Wiki snapshot**. GitHub Actions statically compiles this module and checks the current units, but **does not claim production MCP authorization from skipped offline unit tests**.
- The snapshot Wiki MCP does **not** supply short-lived Paperclip `runtimeMcp` grants or privileged production task rights to Hermes. A real Paperclip-issued run must establish agent/run-bound tool permissions and same-run Opik traces before production adapter migration; see canonical [PR #28](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/28) and [PR #18](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/18).
- Current readiness result: `PRE_CUTOVER_BLOCKED`. The `health/readiness.sh` entry uses the single installed fail-closed verifier, not the retired POC profile.

## Rollback

Stop only the current `hermes-paperclip-wiki-sync.timer` if restoring a prior verified deployment; retain the authoritative Paperclip Wiki and current Hermes persistent data. Do not delete snapshots or change unrelated agent configurations. Restore the independently approved prior unit files and source from Git and verify readback. Historical `Hermes Test` POC instructions remain available in Git history, not as runnable production documentation.
