#!/usr/bin/env bash
set -euo pipefail
umask 077
if [[ "$(id -un)" != 'multica-zar' ]]; then echo MCP_RUN_USER_INVALID >&2; exit 70; fi
if [[ -z "${CREDENTIALS_DIRECTORY:-}" ]]; then echo MCP_SYSTEMD_CREDENTIAL_MISSING >&2; exit 77; fi
TOKEN_FILE="$CREDENTIALS_DIRECTORY/coolify_readonly"
if [[ ! -f "$TOKEN_FILE" || -L "$TOKEN_FILE" || ! -r "$TOKEN_FILE" ]]; then echo MCP_READONLY_TOKEN_MISSING >&2; exit 77; fi
export COOLIFY_ACCESS_TOKEN_FILE="$TOKEN_FILE"
unset COOLIFY_ACCESS_TOKEN
export COOLIFY_BASE_URL='http://127.0.0.1:8001'
export COOLIFY_MCP_REQUIRE_HUMAN='on'
exec /usr/bin/node /opt/multica-tools/coolify-harness-ro/node_modules/@masonator/coolify-mcp/dist/index.js
