"""Precisely select affected versioned Harness Compose migration candidates.
Advisory output only: this code never calls Docker, GitHub or Coolify.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "ops" / "compose-migration-candidates.json"
GLOBAL_CONTRACTS = {
    "ops/service-build-roots.json",
    "ops/compose-migration-candidates.json",
    "scripts/select_owned_compose.py",
    "scripts/test_owned_compose_candidates.py",
}

def select(changed_paths):
    changes = set()
    for path in changed_paths:
        item = path.strip()
        if item.startswith("./"):
            item = item[2:]
        if item:
            changes.add(item)
    rows = json.loads(INVENTORY.read_text(encoding="utf-8"))["resources"]
    if changes.intersection(GLOBAL_CONTRACTS):
        return sorted(r["id"] for r in rows)
    return sorted(r["id"] for r in rows
                  if any(path.startswith(prefix)
                         for path in changes for prefix in r["watch_paths"]))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--changed-file", required=True, type=Path)
    args = parser.parse_args()
    changed = args.changed_file.read_text(encoding="utf-8").splitlines()
    print(json.dumps({
        "selected": select(changed),
        "release_authorized": False,
        "decision": "selection-only; release gates remain in existing controller",
    }, sort_keys=True))

if __name__ == "__main__":
    main()
