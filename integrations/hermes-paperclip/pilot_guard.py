#!/usr/bin/env python3
"""Fail-closed Paperclip adapter inventory guard for Hermes Test pilot.

Only a sanitized readback of GET /api/companies/{companyId}/agents is needed.
No API tokens, secret values, network access, subprocesses or writes.
The guard intentionally does NOT certify E2E delivery or secret correctness.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PILOT_ID = "456e000b-6574-4c84-8cab-76af49522afc"
PILOT_NAME = "Hermes Test"
PILOT_URL = "https://hermes-poc.zariszlif.pl/p/hermes-test"
ALLOWED_CONTROL = "opencode_local"


def validate_inventory(data: object, *, require_operational: bool = False) -> list[str]:
    problems: list[str] = []
    if isinstance(data, dict):
        agents = data.get("agents")
    else:
        agents = data
    if not isinstance(agents, list) or not agents:
        return ["agents: expected a nonempty list read from Paperclip"]
    ids: set[str] = set()
    pilots = []
    for i, agent in enumerate(agents):
        if not isinstance(agent, dict):
            problems.append(f"agent[{i}]: expected object")
            continue
        aid = agent.get("id")
        if not isinstance(aid, str) or not aid:
            problems.append(f"agent[{i}]: missing id")
            continue
        if aid in ids:
            problems.append(f"agent[{i}]: duplicate id")
        ids.add(aid)
        adapter = agent.get("adapterType")
        if aid == PILOT_ID:
            pilots.append(agent)
            if agent.get("name") != PILOT_NAME:
                problems.append("pilot: unexpected name")
            if adapter != "hermes_gateway":
                problems.append("pilot: must use hermes_gateway")
            config = agent.get("adapterConfig")
            if not isinstance(config, dict):
                problems.append("pilot: adapterConfig must be an object")
                config = {}
            if config.get("apiBaseUrl") != PILOT_URL:
                problems.append("pilot: adapter must target the named /p/hermes-test profile")
            binding = config.get("apiKey")
            if not isinstance(binding, dict) or binding.get("type") != "secret_ref" or not binding.get("secretId"):
                problems.append("pilot: encrypted apiKey secret_ref missing")
            runtime = agent.get("runtimeConfig")
            heartbeat = runtime.get("heartbeat", {}) if isinstance(runtime, dict) else {}
            if heartbeat.get("enabled") is not False:
                problems.append("pilot: heartbeat must remain disabled")
            if heartbeat.get("maxConcurrentRuns") != 1:
                problems.append("pilot: maxConcurrentRuns must be exactly 1")
            if require_operational and agent.get("status") not in {"idle", "running"}:
                problems.append("pilot: not operational; investigate real run evidence")
        elif adapter != ALLOWED_CONTROL:
            problems.append(f"control {aid}: adapter changed before approval ({adapter})")
    if len(pilots) != 1:
        problems.append(f"pilot: expected exactly one matching agent, found {len(pilots)}")
    hermes_ids = [a.get("id") for a in agents if isinstance(a, dict) and a.get("adapterType") == "hermes_gateway"]
    if hermes_ids != [PILOT_ID]:
        problems.append("pilot: exactly one Hermes Gateway agent is permitted")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path, help="Sanitized JSON from Paperclip agents API")
    parser.add_argument("--require-operational", action="store_true")
    args = parser.parse_args()
    try:
        data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"BLOCKED: cannot read snapshot: {exc}", file=sys.stderr)
        return 2
    errors = validate_inventory(data, require_operational=args.require_operational)
    if errors:
        print("BLOCKED: Hermes Test pilot isolation guard failed")
        for error in errors:
            print(f" - {error}")
        return 1
    print("PASS: Hermes Test is the sole Hermes Gateway adapter; all other agents remain on OpenCode.")
    print("NOTE: this validates configuration isolation only, not authenticated Paperclip→Hermes delivery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
