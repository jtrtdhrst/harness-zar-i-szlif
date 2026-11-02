#!/bin/sh
set -eu
SRC="/var/lib/docker/volumes/phime3w5l50scx9q4tjoelcx_paperclip-home/_data/instances/default/skills/9894e3c2-3317-46ca-8c72-7a442a76a78e/comfyui-arkcodex-runner/SKILL.md"
DST="/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data/profiles/cpo/skills/company-managed/comfyui-arkcodex-runner/SKILL.md"
test -f "$SRC" && test ! -L "$SRC" || exit 11
mkdir -p "$(dirname "$DST")"
if test -f "$DST" && cmp -s "$SRC" "$DST"; then echo CPO_ROLE_SKILL_IN_SYNC; exit 0; fi
TEMP=$(mktemp "${DST}.tmp.XXXXXX")
trap 'rm -f "$TEMP"' EXIT
install -m 0444 "$SRC" "$TEMP"
chown 10000:10000 "$TEMP"
cmp -s "$SRC" "$TEMP"
mv -f "$TEMP" "$DST"
cmp -s "$SRC" "$DST"
echo CPO_ROLE_SKILL_UPDATED
