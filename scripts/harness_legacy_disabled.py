#!/usr/bin/env python3
"""Fail-closed replacement at the OLD harness_image_delivery.py host path.

The original root-owned controller ignores per-service HOLD. After the
operator backs it up in the root-private archive, this script must replace
its original executable path. The old path must never deploy again, including
manual --auto invocations or accidental activation of a restored old unit.
This shim has no Docker, network, Coolify or secret dependencies.
"""
import json
import sys


def main(_argv=None):
    print(json.dumps({"result": "denied",
                      "reason": "legacy_hold_blind_controller_disabled"}),
          file=sys.stderr)
    return 78


if __name__ == "__main__":
    raise SystemExit(main())
