#!/usr/bin/env bash
# Rebuild embeddings only after genuinely unwritten content has been generated.
set -euo pipefail
MCP=repowise-mcp-lecwi3emh9hjxir7gphmalie
BASE=/opt/repowise-knowledge
count() { docker exec -i "$MCP" python3 - < "$BASE/unwritten.py" "$1" | wc -l; }
for repo in product harness; do
  before=$(count "$repo")
  "$BASE/refill-pages.sh" "$repo" "$MCP"
  after=$(count "$repo")
  if [ "$after" -lt "$before" ]; then
    timeout 300 docker exec "$MCP" sh -lc "cd /workspace/$repo && repowise reindex --embedder openai" \
      || { echo "REINDEX_FAILED repo=$repo" >&2; exit 1; }
    timeout 120 docker exec "$MCP" sh -lc "cd /workspace/$repo && repowise doctor --repair" >/dev/null 2>&1 \
      || { echo "REINDEX_REPAIR_FAILED repo=$repo" >&2; exit 1; }
    doctor_json=$(timeout 120 docker exec "$MCP" sh -lc "cd /workspace/$repo && repowise doctor --format json" 2>/dev/null) || :
    printf '%s\n' "$doctor_json" | python3 -c 'import json,sys; s=sys.stdin.read(); d=json.loads(s[s.index("{"):]); checks={x["id"]:x["ok"] for x in d["checks"]}; assert checks.get("vector-store-sync") and checks.get("fts-index-sync"); print("REFILL_STORE_OK")' \
      || { echo "REINDEX_STORE_MISMATCH repo=$repo" >&2; exit 1; }
  else
    echo "REINDEX_SKIPPED repo=$repo unwritten=$after"
  fi
done
