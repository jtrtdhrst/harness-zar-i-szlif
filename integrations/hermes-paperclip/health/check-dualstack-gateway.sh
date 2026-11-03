#!/usr/bin/env bash
set -euo pipefail
url='https://hermes-poc.zariszlif.pl/p/cho/v1/runs'
for family in 4 6; do
    hdr="$(mktemp)"
    body="$(mktemp)"
    trap 'rm -f "$hdr" "$body"' EXIT
    code="$(curl -"$family" -sS --connect-timeout 6 --max-time 12 -X POST -H 'Content-Type: application/json' --data '{' -D "$hdr" -o "$body" -w '%{http_code}' "$url")"
    if [ "$code" != 401 ] || ! grep -qi 'application/json' "$hdr" || ! grep -q '"gateway_auth_error"' "$body"; then
        printf 'FAIL ipv%s code=%s origin_json=%s\n' "$family" "$code" "$(grep -qi 'application/json' "$hdr" && echo true || echo false)"
        exit 1
    fi
    printf 'PASS ipv%s HTTPS Cloudflare Access VPS-only bypass; Hermes origin rejected invalid bearer as expected\n' "$family"
    rm -f "$hdr" "$body"
    trap - EXIT
done
