#!/usr/bin/env bash
# Generate all pending concept pages as ONE coherent dependency-closed batch.
# Individual --cascade none calls can re-stale their sibling pages indefinitely.
set -euo pipefail
REPO=${1:?repo}
MCP=${2:?mcp container}
case "$REPO" in harness|product) ;; *) echo "invalid repo" >&2; exit 2 ;; esac
BASE=/opt/repowise-knowledge
pending=$(docker exec -i "$MCP" python3 - < "$BASE/unwritten.py" "$REPO" --pending) || {
  echo "PENDING_SCAN_FAILED repo=$REPO" >&2; exit 1;
}
if [[ -z "$pending" ]]; then
  echo "PAGES_DONE repo=$REPO generated=0 remaining=0"
  exit 0
fi
mapfile -t pages <<< "$pending"
args=(repowise generate -y --cascade full)
for page in "${pages[@]}"; do
  [[ -n "$page" ]] && args+=(--page "$page")
done
echo "PAGE_BATCH_BEGIN repo=$REPO pending=${#pages[@]} $(date -u +%FT%TZ)"
timeout 420 docker exec --workdir "/workspace/$REPO" "$MCP" "${args[@]}" || {
  echo "PAGE_BATCH_FAILED repo=$REPO" >&2; exit 1;
}
remaining=$(docker exec -i "$MCP" python3 - < "$BASE/unwritten.py" "$REPO" --pending | wc -l)
echo "PAGES_DONE repo=$REPO selected=${#pages[@]} remaining=$remaining"
[[ "$remaining" -eq 0 ]] || { echo "PAGES_INCOMPLETE repo=$REPO remaining=$remaining" >&2; exit 1; }
