#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="$repo_root/plasmic"
upstream="$src/upstream"
dest="${1:-$repo_root/.build/plasmic}"
expected="85b861115687fde8e7970a9f270660aecb62b38e"
case "$dest" in "$src"|"$src"/*) echo "Refusing destination inside plasmic source" >&2; exit 1;; esac
if [[ -e "$dest" ]]; then echo "Refusing existing build directory $dest" >&2; exit 1; fi
git -C "$repo_root" submodule update --init -- plasmic/upstream
actual="$(git -C "$upstream" rev-parse HEAD)"
[[ "$actual" == "$expected" ]] || { echo "Unexpected upstream SHA $actual" >&2; exit 1; }
mkdir -p "$(dirname "$dest")"
cp -a "$upstream" "$dest"
rm -f "$dest/.git"
for p in .dockerignore .env.example SELFHOST.md studio.Dockerfile studio/nginx.conf docker-compose.yml platform/wab/src/wab/shared/devflags.ts platform/shared/.keep; do
  mkdir -p "$dest/$(dirname "$p")"
  cp -p "$src/$p" "$dest/$p"
done
# Match omitted upstream paths in the original product snapshot.
rm -f "$dest/.github/workflows/cla.yaml"
rm -f "$dest/packages/react-web/lib/auth/package.json"
rm -f "$dest/packages/react-web/lib/data-sources/package.json"
rm -f "$dest/packages/react-web/lib/host/package.json"
rm -f "$dest/packages/react-web/lib/query/package.json"
rm -f "$dest/platform/sub/.idea/codeStyles/codeStyleConfig.xml"
rm -f "$dest/platform/sub/.idea/compiler.xml"
rm -f "$dest/platform/sub/.idea/encodings.xml"
rm -f "$dest/platform/sub/.idea/inspectionProfiles/Project_Default.xml"
rm -f "$dest/platform/sub/.idea/jsLibraryMappings.xml"
rm -f "$dest/platform/sub/.idea/misc.xml"
rm -f "$dest/platform/sub/.idea/modules.xml"
rm -f "$dest/platform/sub/.idea/sub.iml"
rm -f "$dest/platform/sub/.idea/vcs.xml"
rm -f "$dest/platform/wab/public/static/img/icon_placeholder.svg"
rm -f "$dest/platform/wab/src/wab/gen/.gitkeep"
echo "Generated Plasmic source at $dest (pinned upstream + 8 overrides - 16 files)"
