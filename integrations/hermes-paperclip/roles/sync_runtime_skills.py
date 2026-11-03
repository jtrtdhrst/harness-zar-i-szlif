#!/usr/bin/env python3
"""Read-only by default: sync ONLY pinned Paperclip bundled/core/local desired skills.

Distinct from full-bundle company-managed schema-2 sync. Existing Hermes profiles
never receive unassigned skills. No unapproved file, symlink, bearer or provider
secret is copied. Live source is read-only from the current Paperclip container;
--source-root is used by isolated tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path("/opt/hermes-gateway-ops")
DEST = Path("/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data/profiles")
MANIFEST = ROOT / "runtime-skill-allowlist.json"
COMPANY = "9894e3c2-3317-46ca-8c72-7a442a76a78e"
ROLES = frozenset(("ceo", "cho", "cmo", "coo", "cpo", "cto", "designer",
                   "email-creative", "engineer", "harness-engineer",
                   "lifecycle-ops", "mascot-designer", "mcp-engineer", "ui-qa"))
CORE_KEYS = frozenset((
    "paperclipai/paperclip/paperclip",
    "paperclipai/paperclip/complain",
    "paperclipai/paperclip/suggestion-box",
))
SPECIAL_ASSIGNMENTS = {
    "coo": "paperclipai/bundled/paperclip-operations/status-card-query",
    "harness-engineer": "paperclipai/paperclip/paperclip-opencode-health",
    "email-creative": "local/5ee1f0f6fb/kompas-brand-email",
}
EXPECTED_KEYS = CORE_KEYS | frozenset(SPECIAL_ASSIGNMENTS.values())
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,90}$")
SAFE_ASSET = re.compile(r"^[\w.\-]+(?:/[\w.\-]+)*$")
SHA = re.compile(r"^[a-f0-9]{64}$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_directory(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()


def find_container() -> str:
    names = subprocess.check_output(["docker", "ps", "--format", "{{.Names}}"], text=True).splitlines()
    candidates = [name for name in names if name.startswith("paperclip-2")]
    if len(candidates) != 1:
        raise RuntimeError("Exactly one live Paperclip source container is required")
    return candidates[0]


def verify_manifest(data: dict) -> tuple[dict, dict]:
    roles, sources = data.get("roles"), data.get("sources")
    if data.get("schema_version") != 1 or data.get("company_id") != COMPANY:
        raise ValueError("Pinned runtime skills manifest metadata invalid")
    if not isinstance(roles, dict) or set(roles) != ROLES or not isinstance(sources, dict):
        raise ValueError("Exactly 14 real roles and a pinned source mapping are required")
    selected = set()
    count = 0
    for role, names in roles.items():
        if not isinstance(names, list) or len(set(names)) != len(names):
            raise ValueError("Duplicate or invalid role skill assignment")
        count += len(names)
        selected.update(names)
    if count != 45 or set(sources) != selected or set(sources) != EXPECTED_KEYS:
        raise ValueError("Approved runtime skill assignments must equal the 45 current desired entries")
    for role, keys in roles.items():
        required = CORE_KEYS | ({SPECIAL_ASSIGNMENTS[role]} if role in SPECIAL_ASSIGNMENTS else set())
        if set(keys) != required:
            raise ValueError("UNAUTHORIZED_PROFILE_SKILL_ASSIGNMENT " + role)
    runtime_names = set()
    for key, info in sources.items():
        if not isinstance(info, dict):
            raise ValueError("Skill source must be an object")
        name, source = info.get("runtime_name"), info.get("source_path")
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name) or name in runtime_names:
            raise ValueError("Unsafe or duplicated runtime skill name")
        runtime_names.add(name)
        approved_root = f"/paperclip/instances/default/skills/{COMPANY}"
        exact_sources = {
            "local/5ee1f0f6fb/kompas-brand-email": (
                f"{approved_root}/kompas-brand-email"),
            "paperclipai/bundled/paperclip-operations/status-card-query": (
                f"{approved_root}/__catalog__/status-card-query--5374d5ae20"),
            "paperclipai/paperclip/paperclip-opencode-health": (
                f"{approved_root}/__runtime__/paperclip-opencode-health"),
        }
        allowed_source = (
            source == f"/app/skills/{name}" and key == f"paperclipai/paperclip/{name}"
            or source == exact_sources.get(key)
        )
        if not allowed_source:
            raise ValueError("Source location and key are not on the approved allowlist")
        files = info.get("approved_files_sha256")
        if not isinstance(files, dict) or "SKILL.md" not in files:
            raise ValueError("Missing full-bundle source file pins")
        for rel, checksum in files.items():
            if not isinstance(rel, str) or not SAFE_ASSET.fullmatch(rel) or ".." in Path(rel).parts:
                raise ValueError("Unsafe pinned relative asset path")
            if not isinstance(checksum, str) or not SHA.fullmatch(checksum):
                raise ValueError("Invalid pinned SHA-256")
    return roles, sources


def run(manifest_path: Path = MANIFEST, profiles_root: Path = DEST,
        apply: bool = False, source_root: Path | None = None,
        container: str | None = None) -> dict:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    roles, sources = verify_manifest(data)
    result = {"mode": "APPLY" if apply else "AUDIT", "profiles": len(roles),
              "assignments": sum(len(v) for v in roles.values()), "unique_skills": len(sources)}
    with tempfile.TemporaryDirectory(prefix="paperclip-runtime-skill-audit-") as temp:
        base = Path(temp)
        source_dirs = {}
        if source_root is None:
            live = container or find_container()
            for key, spec in sorted(sources.items()):
                dest = base / spec["runtime_name"]
                dest.mkdir()
                subprocess.run(["docker", "cp", f'{live}:{spec["source_path"]}/.', str(dest)],
                               check=True, capture_output=True, text=True, timeout=20)
                source_dirs[key] = dest
        else:
            for key, spec in sources.items():
                source_dirs[key] = source_root / spec["runtime_name"]
        # Validate ALL source trees and pin sets before writing ANY target.
        files_by_key = {}
        for key, folder in source_dirs.items():
            if not safe_directory(folder):
                raise ValueError("Source bundle directory missing or symlinked")
            seen = {}
            for asset in folder.rglob("*"):
                if asset.is_symlink():
                    raise ValueError("Symlink in approved Paperclip source bundle")
                if not asset.is_file():
                    continue
                relative = asset.relative_to(folder).as_posix()
                if not SAFE_ASSET.fullmatch(relative) or ".." in Path(relative).parts:
                    raise ValueError("Unsafe Paperclip skill asset")
                if asset.stat().st_size > 2_000_000:
                    raise ValueError("Oversized Paperclip skill asset")
                seen[relative] = digest(asset)
            if seen != sources[key]["approved_files_sha256"]:
                raise ValueError("UNAPPROVED_SOURCE_SHA " + key)
            files_by_key[key] = sorted(seen)

        plan, extras = [], []
        for role, skills in sorted(roles.items()):
            role_base = profiles_root / role / "skills" / "paperclip-managed"
            if role_base.exists() and not safe_directory(role_base):
                raise ValueError("Unsafe per-profile destination " + role)
            parent = role_base.parent
            if not safe_directory(parent):
                raise ValueError("Invalid per-profile skills parent " + role)
            allowed_names = {sources[k]["runtime_name"] for k in skills}
            for folder in (role_base.iterdir() if role_base.is_dir() else ()):

                if folder.is_symlink() or folder.name not in allowed_names:
                    extras.append({"role": role, "name": folder.name})
            for key in skills:
                spec = sources[key]
                name = spec["runtime_name"]
                skill_base = role_base / name
                if skill_base.exists() and not safe_directory(skill_base):
                    raise ValueError("Unsafe per-role skill bundle directory")
                for rel in files_by_key[key]:
                    path = skill_base / rel
                    for parent in (path, *path.parents):
                        if parent == role_base.parent:
                            break
                        if parent.is_symlink():
                            raise ValueError("Symlink in destination skill path")
                    if path.exists() and not path.is_file():
                        raise ValueError("Non-file destination asset")
                    previous = digest(path) if path.is_file() else None
                    expected = spec["approved_files_sha256"][rel]
                    plan.append({"role": role, "key": key, "asset": rel, "source": source_dirs[key] / rel,
                                 "target": path, "sha": expected, "state": (
                                     "match" if previous == expected else "missing" if previous is None else "drift")})
                if skill_base.is_dir():
                    allowed_assets = set(files_by_key[key])
                    for asset in skill_base.rglob("*"):
                        if asset.is_symlink():
                            raise ValueError("Symlink in destination skill tree")
                        if asset.is_file() and asset.relative_to(skill_base).as_posix() not in allowed_assets:
                            extras.append({"role": role, "name": name, "asset": asset.relative_to(skill_base).as_posix()})
        changes = [p for p in plan if p["state"] != "match"]
        if extras:
            raise ValueError("UNAPPROVED_DESTINATION_FILES " + str(len(extras)))
        if apply:
            for item in changes:
                target = item["target"]
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                if target.parent.is_symlink():
                    raise ValueError("Unsafe target parent")
                fd, temp_path = tempfile.mkstemp(prefix=".paperclip-bundle-", dir=target.parent)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(item["source"].read_bytes())
                        stream.flush()
                        os.fsync(stream.fileno())
                    if os.geteuid() == 0:
                        os.chown(temp_path, 10000, 10000)
                    os.chmod(temp_path, 0o555 if item["source"].stat().st_mode & 0o111 else 0o444)
                    if digest(Path(temp_path)) != item["sha"]:
                        raise RuntimeError("Staged skill asset SHA mismatch")
                    os.replace(temp_path, target)
                finally:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
            for item in plan:
                if not item["target"].is_file() or digest(item["target"]) != item["sha"]:
                    raise RuntimeError("Post-copy skill asset SHA mismatch")
        result.update(files_checked=len(plan), mismatched_before=len(changes),
                      mismatched_after=0 if apply else len(changes),
                      missing_files=sum(p["state"] == "missing" for p in changes),
                      drift_files=sum(p["state"] == "drift" for p in changes),
                      differences=[{k: p[k] for k in ("role", "key", "asset", "state")}
                                   for p in changes[:25]])
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--profiles-root", type=Path, default=DEST)
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = run(args.manifest, args.profiles_root, args.apply, args.source_root)
    print(json.dumps(result, ensure_ascii=False))
    if result["mismatched_after"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
