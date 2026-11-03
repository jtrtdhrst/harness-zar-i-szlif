#!/usr/bin/env bash
# One current production readback gate. The retired hermes-test actor must not
# be used as a proxy for 14 real Paperclip -> Hermes Gateway acceptance.
set -euo pipefail
GATE="/opt/hermes-paperclip-sync/e2e-verify.sh"
if [ ! -x "$GATE" ]; then
  echo "BLOCKED: production verifier absent; never infer E2E readiness" >&2
  exit 2
fi
exec "$GATE"
