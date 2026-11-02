#!/bin/sh
set -eu
GATEWAY="$(docker ps --filter name=2sganhxhhnioiqh4an9g2f4k --format '{{.Names}}' | head -1)"
test -n "$GATEWAY"
test "$(docker inspect --format '{{.State.Health.Status}}' "$GATEWAY")" = healthy
systemctl is-active --quiet hermes-test-wiki-sync.timer
systemctl is-active --quiet hermes-cpo-role-skill-sync.timer
ROOT_PAPERCLIP=/var/lib/docker/volumes/phime3w5l50scx9q4tjoelcx_paperclip-home/_data
ROOT_HERMES=/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data
cmp -s "$ROOT_PAPERCLIP/instances/default/data/wiki-root/wiki/concepts/karta-zbiorki.md" "$ROOT_HERMES/wiki-paperclip-test/wiki/concepts/karta-zbiorki.md"
cmp -s "$ROOT_PAPERCLIP/instances/default/skills/9894e3c2-3317-46ca-8c72-7a442a76a78e/comfyui-arkcodex-runner/SKILL.md" "$ROOT_HERMES/profiles/cpo/skills/company-managed/comfyui-arkcodex-runner/SKILL.md"
docker exec "$GATEWAY" /opt/hermes/.venv/bin/python -c "from pathlib import Path; from hermes_yaml import safe_load; import json; p=Path('/opt/data/profiles/cpo'); c=safe_load((p/'config.yaml').read_text()); h=json.loads((p/'hindsight/config.json').read_text()); assert 'wiki_fs' in c.get('platform_toolsets',{}).get('api_server',[]); assert c['mcp_servers']['wiki_fs']['enabled']; assert h['bank_id']=='hermes-cpo'; assert (p/'plugins/opik/plugin.yaml').is_file()"
docker exec "$GATEWAY" /opt/hermes/.venv/bin/python -c "import urllib.request,urllib.error; u='http://127.0.0.1:8642/p/cpo/v1/models'; ok=False
try: urllib.request.urlopen(u, timeout=5)
except urllib.error.HTTPError as e: ok=(e.code==401)
assert ok, 'CPO Gateway API auth guard missing'"
echo "CPO_PROFILE_READY: Gateway auth guard, scoped skills, Wiki mirror, bank configuration and Opik plugin PASS (readiness only)"
