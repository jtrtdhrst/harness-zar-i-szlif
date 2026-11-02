#!/usr/bin/env python3
"""Sync explicitly approved Paperclip company skills into isolated Hermes profiles.

Default is read-only audit. --apply performs idempotent, atomic SKILL.md copies
and reports SHA-256. No Paperclip Core, agent model, gateway secret or cron writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

SRC_BASE = Path(
    "/var/lib/docker/volumes/phime3w5l50scx9q4tjoelcx_paperclip-home"
    "/_data/instances/default/skills"
)
DST_BASE = Path(
    "/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data"
    "/_data/profiles"
)
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(manifest_file: Path, apply: bool, source: Path, profiles: Path) -> dict:
    doc = json.loads(manifest_file.read_text("utf-8"))
    roles = doc.get("profiles")
    company = doc.get("source_company_id")
    if (doc.get("schema_version") != 1 or len(roles or {}) != 14
            or not isinstance(company, str) or not re.fullmatch(r"[0-9a-f-]{36}", company)):
        raise ValueError("Invalid allowlist manifest")
    company_src = source / company
    pins = doc.get("approved_sha256")
    all_skills = set(skill for names in roles.values() for skill in names)
    if (not isinstance(pins, dict) or set(pins) != all_skills
            or any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v)
                   for v in pins.values())):
        raise ValueError("Approved SHA-256 manifest is missing or incomplete")
    plan = []
    for role, skills in sorted(roles.items()):
        if not SAFE_NAME.fullmatch(role) or not isinstance(skills, list):
            raise ValueError("Invalid role or skills")
        if len(skills) != len(set(skills)):
            raise ValueError("Duplicate role skills: " + role)
        dst_parent = profiles / role / "skills" / "company-managed"
        if not dst_parent.is_dir() or dst_parent.is_symlink():
            raise ValueError("Missing/unsafe skill destination: " + role)
        for skill in skills:
            if not isinstance(skill, str) or not SAFE_NAME.fullmatch(skill):
                raise ValueError("Invalid skill key: " + str(skill))
            src_dir = company_src / skill
            src = src_dir / "SKILL.md"
            dst_dir = dst_parent / skill
            dst = dst_dir / "SKILL.md"
            if (not src.is_file() or src.is_symlink()
                    or src_dir.is_symlink() or src.stat().st_size > 1024 * 1024):
                raise ValueError("Missing, linked or oversized canonical skill: " + skill)
            if dst_dir.exists() and (not dst_dir.is_dir() or dst_dir.is_symlink()):
                raise ValueError("Unsafe destination dir: " + str(dst_dir))
            if dst.exists() and (not dst.is_file() or dst.is_symlink()):
                raise ValueError("Unsafe destination file: " + str(dst))
            old_sha = sha(dst) if dst.is_file() else None
            source_sha = sha(src)
            if source_sha != pins[skill]:
                raise RuntimeError("UNAPPROVED_SOURCE_SHA: " + role + "/" + skill)
            plan.append({
                "role": role,
                "skill": skill,
                "source_sha256": source_sha,
                "old_sha256": old_sha,
                "state": "match" if old_sha == source_sha else ("missing" if old_sha is None else "drift"),
                "_src": src,
                "_dst_dir": dst_dir,
                "_dst": dst,
            })
    if apply:
        for item in plan:
            if item["state"] == "match":
                continue
            src, dest_dir, dest = item["_src"], item["_dst_dir"], item["_dst"]
            dest_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
            if dest_dir.is_symlink():
                raise ValueError("Destination is symlink")
            fd, tmp = tempfile.mkstemp(prefix=".skill-sync-", dir=dest_dir)
            try:
                with os.fdopen(fd, "wb") as output:
                    output.write(src.read_bytes())
                    output.flush()
                    os.fsync(output.fileno())
                os.chown(tmp, 10000, 10000)
                os.chmod(tmp, 0o444)
                if sha(Path(tmp)) != item["source_sha256"]:
                    raise RuntimeError("SHA mismatch during copy")
                os.replace(tmp, dest)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            if sha(dest) != item["source_sha256"]:
                raise RuntimeError("Post-copy SHA mismatch: " + item["role"] + "/" + item["skill"])
        for item in plan:
            if sha(item["_dst"]) != item["source_sha256"]:
                raise RuntimeError("Post-apply role skill drift")
    summary = {
        "mode": "APPLY" if apply else "AUDIT",
        "profiles": len(roles),
        "skills_checked": len(plan),
        "mismatched_before": sum(x["state"] != "match" for x in plan),
        "mismatched_after": 0 if apply else sum(x["state"] != "match" for x in plan),
        "differences": [
            {"profile": x["role"], "skill": x["skill"], "state": x["state"],
             "sha256": x["source_sha256"]}
            for x in plan if x["state"] != "match"
        ],
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("profile-skill-allowlist.json"))
    parser.add_argument("--source-root", type=Path, default=SRC_BASE)
    parser.add_argument("--profiles-root", type=Path, default=DST_BASE)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = run(args.manifest, args.apply, args.source_root, args.profiles_root)
    print(json.dumps(result, ensure_ascii=False))
    if result["mismatched_after"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
