#!/usr/bin/env bash
# Regenerate unwritten AND source-stale model pages. Report failures, no silent success.
set -euo pipefail
REPO=$1
MCP=$2
case "$REPO" in harness|product) ;; *) echo "invalid repo" >&2; exit 2 ;; esac
BASE=/opt/repowise-knowledge
pending=$(docker exec -i "$MCP" python3 - < "$BASE/unwritten.py" "$REPO" --pending) || { echo "PENDING_SCAN_FAILED repo=$REPO" >&2; exit 1; }
if [[ -z "$pending" ]]; then
  echo "PAGES_DONE repo=$REPO generated=0 remaining=0"
  exit 0
fi
mapfile -t pages <<< "$pending"
generated=0
for page in "${pages[@]}"; do
  [[ -n "$page" ]] || continue
  echo "PAGE_BEGIN repo=$REPO page=$page $(date -u +%FT%TZ)"
  # Avoid shell interpolation of repository-derived page names.
  timeout 420 docker exec --workdir "/workspace/$REPO" "$MCP" repowise generate -y --cascade none --page "$page" >/dev/null 2>&1 \
    || { echo "PAGE_FAILED repo=$REPO page=$page" >&2; exit 1; }
  ((generated+=1))
done
remaining=$(docker exec -i "$MCP" python3 - < "$BASE/unwritten.py" "$REPO" --pending | wc -l)
echo "PAGES_DONE repo=$REPO generated=$generated remaining=$remaining"
[[ "$remaining" -eq 0 ]] || { echo "PAGES_INCOMPLETE repo=$REPO remaining=$remaining" >&2; exit 1; }
