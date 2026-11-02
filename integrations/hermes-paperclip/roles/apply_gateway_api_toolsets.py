#!/usr/bin/env python3
"""Safely validate/apply scoped Hermes Gateway API toolsets for named profiles.

No Paperclip writes, no provider changes, no model migration, no timers.
Requires PyYAML on the VPS. Default dry run; explicit --apply required.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

import yaml

ROOT_DEFAULT = Path(
    "/var/lib/docker/volumes/"
    "2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data/profiles"
)
DENIED = frozenset(
    ("hermes-cli", "terminal", "file", "code_execution", "computer_use",
     "cronjob", "delegation", "browser", "session_search", "connections")
)
SAFE = frozenset(
    ("clarify", "image_gen", "memory", "skills", "todo", "tts",
     "vision", "web", "wiki_fs")
)


def check_manifest(path: Path) -> dict[str, list[str]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema_version") != 1 or not isinstance(doc.get("profiles"), dict):
        raise RuntimeError("Unsupported manifest schema")
    roles = doc["profiles"]
    if len(roles) != 14:
        raise RuntimeError("Expected exactly 14 active profiles")
    for profile, items in roles.items():
        if (not isinstance(items, list) or len(set(items)) != len(items)
                or not {"memory", "skills", "wiki_fs"} <= set(items)
                or not set(items) <= SAFE or set(items) & DENIED):
            raise RuntimeError("Invalid API toolset for " + profile)
    return roles


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name(
        "gateway-api-toolsets.json"))
    parser.add_argument("--profiles-root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--backup-dir", type=Path, default=Path(
        "/opt/hermes-profile-cutover-backup-20261102/api-allowlist"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    roles = check_manifest(args.manifest)
    changes = []
    for role, allow in sorted(roles.items()):
        path = args.profiles_root / role / "config.yaml"
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("Profile config missing: " + role)
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise RuntimeError("Invalid config for " + role)
        bank_file = args.profiles_root / role / "hindsight/config.json"
        bank = json.loads(bank_file.read_text())["bank_id"]
        if bank != "hermes-" + role:
            raise RuntimeError("Incorrect Hindsight bank: " + role)
        wiki = record.get("mcp_servers", {}).get("wiki_fs", {})
        if wiki.get("args", [])[-2:] != ["--profile", role]:
            raise RuntimeError("Scoped Wiki not configured: " + role)
        if set(record.get("platform_toolsets", {}).get("api_server", [])) & DENIED:
            raise RuntimeError("Current API toolset still unsafe: " + role)
        nextrecord = dict(record)
        nexttools = dict(record.get("platform_toolsets", {}))
        before = nexttools.get("api_server", [])
        nexttools["api_server"] = allow
        nextrecord["platform_toolsets"] = nexttools
        changes.append((role, path, record, nextrecord, before, allow))
    if args.apply:
        args.backup_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
        updated = []
        try:
            for role, path, old, new, before, allow in changes:
                snapshot = args.backup_dir / (role + "-config.yaml")
                if not snapshot.exists():
                    shutil.copy2(path, snapshot)
                    os.chmod(snapshot, 0o600)
                st = path.stat()
                fd, tmp = tempfile.mkstemp(prefix=".hermes-api-scope-", dir=path.parent)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    yaml.safe_dump(new, stream, sort_keys=False, allow_unicode=True)
                os.chown(tmp, st.st_uid, st.st_gid)
                os.chmod(tmp, stat.S_IMODE(st.st_mode))
                parsed = yaml.safe_load(Path(tmp).read_text())
                if parsed["model"] != old["model"]:
                    raise RuntimeError("Model unexpectedly changed: " + role)
                if parsed["platform_toolsets"]["api_server"] != allow:
                    raise RuntimeError("API scope unexpectedly changed: " + role)
                os.replace(tmp, path)
                updated.append((path, snapshot))
        except BaseException:
            for path, snapshot in reversed(updated):
                shutil.copy2(snapshot, path)
            raise
    print(json.dumps({
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "verified_banks": 14,
        "verified_scoped_wiki": 14,
        "profiles": [{
            "profile": role, "before": before, "after": after,
            "changed": before != after,
        } for role, _, _, _, before, after in changes],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
