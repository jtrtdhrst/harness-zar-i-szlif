#!/usr/bin/env bash
# Generate genuinely unwritten RepoWise pages; fail visibly on any provider error.
set -euo pipefail
REPO=${1:?repo}
MCP=${2:?mcp container}
BASE=/opt/repowise-knowledge
mapfile -t pages < <(docker exec -i "$MCP" python3 - < "$BASE/unwritten.py" "$REPO")
for page in "${pages[@]}"; do
  [[ -n $page ]] || continue
  echo "PAGE_BEGIN repo=$REPO page=$page $(date -u +%FT%TZ)"
  timeout 420 docker exec "$MCP" sh -lc "cd /workspace/$REPO && repowise generate -y --cascade none --page '$page'" >/dev/null 2>&1 \
    || { echo "PAGE_FAILED repo=$REPO page=$page" >&2; exit 1; }
done
echo "PAGES_DONE repo=$REPO remaining=$(docker exec -i "$MCP" python3 - < "$BASE/unwritten.py" "$REPO" | wc -l)"
