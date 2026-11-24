#!/usr/bin/env bash
# Drain stale/unwritten model pages; reindex semantic vectors only after actual writes.
set -euo pipefail
MCP=repowise-mcp-lecwi3emh9hjxir7gphmalie
BASE=/opt/repowise-knowledge
# The systemd fast-freshness drop-in already holds the GitHub sync lock.
count() { docker exec -i "$MCP" python3 - < "$BASE/unwritten.py" "$1" --pending | wc -l; }
for repo in product harness; do
  # Full/code-only updates can leave deleted source-keyed flow pages stale.
  # Retire only paths proven absent from committed Git HEAD; keep the prose
  # as tombstones so historical evidence survives without polluting retrieval.
  retired_json=$(docker exec -i "$MCP" python3 - "$repo" --apply < "$BASE/repowise_retire_orphan_flows.py") || {
    echo "ORPHAN_RECONCILE_FAILED repo=$repo" >&2; exit 1;
  }
  retired=$(python3 -c 'import json,sys; print(int(json.load(sys.stdin)["retired"]))' <<< "$retired_json")
  echo "ORPHAN_FLOW_RETIRED repo=$repo count=$retired"
  before=$(count "$repo")
  "$BASE/refill-pages.sh" "$repo" "$MCP"
  after=$(count "$repo")
  if [[ "$after" -ne 0 ]]; then
    echo "PAGES_INCOMPLETE repo=$repo remaining=$after" >&2; exit 1
  fi
  if [[ "$before" -gt 0 || "$retired" -gt 0 ]]; then
    timeout 300 docker exec --workdir "/workspace/$repo" "$MCP" repowise reindex --embedder openai >/dev/null 2>&1 \
      || { echo "REINDEX_FAILED repo=$repo" >&2; exit 1; }
    echo "REINDEX_DONE repo=$repo regenerated=$before"
  else
    echo "REINDEX_SKIPPED repo=$repo pending=0"
  fi
done
