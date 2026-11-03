#!/bin/sh
set -eu
export GIT_TERMINAL_PROMPT=0
export GH_PROMPT_DISABLED=1
PAPERCLIP_GITHUB_APP_TOKEN_FILE=/paperclip/github-auth-bin/installation-token.json
export PAPERCLIP_GITHUB_APP_TOKEN_FILE
if [ "$(id -u)" -ne 0 ]; then
 echo "GitHub App gateway startup requires root bootstrap" >&2
 exit 1
fi
if [ ! -s "$PAPERCLIP_GITHUB_APP_TOKEN_FILE" ]; then
 echo "Scoped installation token unavailable; refusing to start gateway" >&2
 exit 1
fi
# No static GitHub token is propagated into the gateway process.
unset GH_TOKEN GITHUB_TOKEN PAPERCLIP_GIT_TOKEN
exec /usr/local/bin/paperclip-mcp-entrypoint.sh "$@"
