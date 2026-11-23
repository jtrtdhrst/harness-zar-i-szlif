#!/bin/bash
# Re-apply durable custom_nodes changes (volume-persisted, idempotent).
# Run after volume restore with COMFY_CTN set to the exact Docker container name.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$(cd "$HERE/.." && pwd)"
COMFY_CTN="${COMFY_CTN:-comfyui}"

# Fail before touching a live container if this checkout is incomplete.
for source in "$HERE/qc_reject_patch.py" "$HERE/llm_json_tolerant_patch.py" \
              "$BASE/canvas-bridge/__init__.py" "$BASE/canvas-bridge/comfy_bridge.py"; do
    if [[ ! -f "$source" ]]; then
        printf 'Missing source: %s\n' "$source" >&2
        exit 1
    fi
done
if ! sudo -n docker inspect "$COMFY_CTN" >/dev/null 2>&1; then
    printf 'Container unavailable: %s (set COMFY_CTN to exact name)\n' "$COMFY_CTN" >&2
    exit 1
fi

run() {
    sudo -n docker cp "$HERE/$1" "$COMFY_CTN:/tmp/$1"
    sudo -n docker exec "$COMFY_CTN" python3 "/tmp/$1" "/app/custom_nodes/comfyui-arkennemasis/$2"
}
putfile() {
    sudo -n docker exec "$COMFY_CTN" mkdir -p "/app/custom_nodes/comfyui-arkennemasis/$(dirname "$2")"
    sudo -n docker cp "$BASE/canvas-bridge/$1" "$COMFY_CTN:/app/custom_nodes/comfyui-arkennemasis/$2"
}
run qc_reject_patch.py variation/qc.py
run llm_json_tolerant_patch.py codex_provider/llm.py
putfile __init__.py mcp_service/__init__.py
putfile comfy_bridge.py mcp_service/comfy_bridge.py
echo "custom_nodes changes applied (idempotent, safe to re-run)"
