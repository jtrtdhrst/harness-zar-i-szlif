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
  else
    echo "REINDEX_SKIPPED repo=$repo unwritten=$after"
  fi
done
