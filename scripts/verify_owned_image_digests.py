"""Require actual immutable OCI digests before any Compose candidate promotion.
This is validation only, never authorization or deployment.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "ops" / "compose-migration-candidates.json"
DIGEST_IMAGE = re.compile(r"^[A-Za-z0-9._:/-]+@sha256:[a-f0-9]{64}$")

def validate_ref(value):
    return isinstance(value, str) and bool(DIGEST_IMAGE.fullmatch(value))

def check(resource_ids=None, env=None):
    if env is None:
        env = os.environ
    rows = json.loads(REGISTRY.read_text(encoding="utf-8"))["resources"]
    ids = set(resource_ids or [row["id"] for row in rows])
    found = set()
    errors = []
    for row in rows:
        if row["id"] not in ids:
            continue
        found.add(row["id"])
        contract = json.loads((ROOT / row["contract"]).read_text(encoding="utf-8"))
        if contract["uuid"] != row["uuid"] or contract["release_state"] != "BLOCKED":
            errors.append(row["id"] + ": invalid immutable ownership contract")
        for requirement in contract["required_digest_images"]:
            key = requirement["key"]
            if not validate_ref(env.get(key)):
                errors.append(row["id"] + ": missing or invalid sha256 digest in " + key)
    for missing in sorted(ids - found):
        errors.append("unknown resource: " + missing)
    return errors

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", action="append", dest="ids",
                        help="Resource ID; repeat for many. Default: all 20.")
    args = parser.parse_args()
    errors = check(args.ids)
    print(json.dumps({"image_digests_valid": not errors,
                      "release_authorized": False,
                      "errors": errors}, sort_keys=True))
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
