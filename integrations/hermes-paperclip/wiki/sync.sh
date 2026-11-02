#!/usr/bin/env bash
set -euo pipefail
SRC="/var/lib/docker/volumes/phime3w5l50scx9q4tjoelcx_paperclip-home/_data/instances/default/data/wiki-root"
DST="/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data/wiki-paperclip-test"
test -d "${SRC}/wiki" || { echo "Wiki source unavailable" >&2; exit 1; }
mkdir -p "${DST}"
find "${DST}" -type d -exec chmod 0755 "{}" +
find "${DST}" -type f -exec chmod 0644 "{}" +
rsync -rt --delete --delete-delay --prune-empty-dirs --include="*/" --include="*.md" --exclude="*" "${SRC}/" "${DST}/"
find "${DST}" -type f -exec chmod 0444 "{}" +
find "${DST}" -type d -exec chmod 0555 "{}" +
printf "FILES=%s\n" "$(find "${DST}" -type f -name "*.md" | wc -l)"
