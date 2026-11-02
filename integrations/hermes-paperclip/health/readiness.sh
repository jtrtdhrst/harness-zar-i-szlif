#!/usr/bin/env bash
set -euo pipefail
SRC="/var/lib/docker/volumes/phime3w5l50scx9q4tjoelcx_paperclip-home/_data/instances/default/data/wiki-root/wiki/concepts/karta-zbiorki.md"
DST="/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data/wiki-paperclip-test/wiki/concepts/karta-zbiorki.md"
systemctl is-active --quiet hermes-test-wiki-sync.timer
test "$(systemctl show hermes-test-wiki-sync.service -p Result --value)" = success
test -f "$SRC" && test -f "$DST"
cmp -s "$SRC" "$DST" || { echo "WIKI_MIRROR_DIVERGED" >&2; exit 10; }
HERMES="$(docker ps --filter name=2sganhxhhnioiqh4an9g2f4k --format "{{.Names}}" | head -1)"
MCP="$(docker ps --filter name=paperclip-mcp-gevr1m6rdj4t4fbhcjvqv8gg --format "{{.Names}}" | head -1)"
test -n "$HERMES" && test -n "$MCP"
test "$(docker inspect --format "{{.State.Health.Status}}" "$HERMES")" = healthy
test "$(docker inspect --format "{{.State.Health.Status}}" "$MCP")" = healthy
docker exec "$HERMES" /opt/hermes/.venv/bin/python -c "from pathlib import Path; p=Path('/opt/data/profiles/hermes-test/config.yaml').read_text(); assert 'wiki_fs' in p and 'mcp-paperclip_knowledge' in p; assert Path('/opt/data/mcp/wiki_readonly.py').is_file()"
docker exec paperclip-2omzqpy8dxgmhuwfbzo7bvvv node -e "let r=await fetch('http://paperclip-mcp:3101/health',{signal:AbortSignal.timeout(3000)});if(!r.ok)process.exit(11)"
echo "HERMES_TEST_READY: gateway, internal Paperclip MCP, Wiki checksum, sync timer and profile configuration PASS"
