#!/usr/bin/env bash
# Drain stale/unwritten model pages, then reindex after meaningful regeneration.
# The installed systemd fast-freshness drop-in holds the GitHub sync lock for
# the duration of this operation to prevent source/index races.
set -euo pipefail
MCP=repowise-mcp-lecwi3emh9hjxir7gphmalie
BASE=/opt/repowise-knowledge
count() { docker exec -i "$MCP" python3 - < "$BASE/unwritten.py" "$1" --pending | wc -l; }
for repo in product harness; do
  before=$(count "$repo")
  "$BASE/refill-pages.sh" "$repo" "$MCP"
  after=$(count "$repo")
  if [[ "$after" -ne 0 ]]; then
    echo "PAGES_INCOMPLETE repo=$repo remaining=$after" >&2; exit 1
  fi
  if [[ "$before" -gt 0 ]]; then
    timeout 300 docker exec --workdir "/workspace/$repo" "$MCP" repowise reindex --embedder openai >/dev/null 2>&1 \
      || { echo "REINDEX_FAILED repo=$repo" >&2; exit 1; }
    echo "REINDEX_DONE repo=$repo regenerated=$before"
  else
    echo "REINDEX_SKIPPED repo=$repo pending=0"
  fi
done
