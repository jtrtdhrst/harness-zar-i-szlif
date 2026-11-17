#!/usr/bin/env python3
"""Fail-closed seed validation for the RepoWise GitHub sync.

A staged seed may proceed only with a full git tier and a finished upgrade.
RepoWise reports "not_applicable" when the seed is already full, so treating
only "complete" as valid blocks every sync after the first full index.
"""
import json
import sys
from pathlib import Path

FULL_TIER = "full"
VALID_UPGRADE = frozenset({"complete", "not_applicable"})


def failure_reason(state_path):
    try:
        state = json.loads(Path(state_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return f"unreadable state.json: {exc}"
    if state.get("git_tier") != FULL_TIER:
        return f"git_tier={state.get('git_tier')!r}"
    status = ((state.get("index_scope") or {}).get("upgrade") or {}).get("status")
    if status not in VALID_UPGRADE:
        return f"upgrade.status={status!r}"
    return None


def main(argv):
    if len(argv) != 2:
        print("usage: repowise_sync_gate.py STATE_JSON", file=sys.stderr)
        return 2
    reason = failure_reason(argv[1])
    if reason:
        print(f"stage-seed-not-full: {reason}", file=sys.stderr)
        return 1
    print(f"stage-seed-full: {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
