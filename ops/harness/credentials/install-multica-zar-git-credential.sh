#!/usr/bin/env bash
# Root-only, digest-pinned replacement of the existing Git credential helper.
set -euo pipefail
[[ "$(id -u)" == "0" ]] || { echo "root required" >&2; exit 2; }
SOURCE="$(dirname "$(readlink -f "$0")")/multica-zar-git-credential"
DEST=/usr/local/libexec/multica-zar-git-credential
EXPECTED_SHA256="f4273a3b2ea364163d49286d1ea57fe8ce1f441968ee1b1eae9ce24ad075c955"
[[ -f "$SOURCE" && ! -L "$SOURCE" && -f "$DEST" && ! -L "$DEST" ]] || { echo "unsafe source or destination" >&2; exit 2; }
ACTUAL_SHA256="$(sha256sum "$SOURCE" | cut -d ' ' -f 1)"
[[ "$ACTUAL_SHA256" == "$EXPECTED_SHA256" ]] || { echo "reviewed source digest mismatch" >&2; exit 2; }
if cmp -s "$SOURCE" "$DEST"; then echo "already installed"; exit 0; fi
BACKUP_DIR=/var/backups/multica-zar-git-credential
install -d -m 0700 -o root -g root "$BACKUP_DIR"
BACKUP="$BACKUP_DIR/previous-$(date -u +%Y%m%dT%H%M%SZ)-$$"
install -m 0600 -o root -g root "$DEST" "$BACKUP"
TEMP="$(mktemp /usr/local/libexec/.multica-zar-git-credential.XXXXXX)"
trap 'rm -f "$TEMP"' EXIT
install -m 0755 -o root -g root "$SOURCE" "$TEMP"
[[ "$(sha256sum "$TEMP" | cut -d ' ' -f 1)" == "$EXPECTED_SHA256" ]] || exit 2
mv -fT "$TEMP" "$DEST"
trap - EXIT
[[ "$(sha256sum "$DEST" | cut -d ' ' -f 1)" == "$EXPECTED_SHA256" ]]
echo "installed digest-pinned helper"
