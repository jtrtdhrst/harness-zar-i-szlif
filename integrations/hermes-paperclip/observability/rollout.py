#!/usr/bin/env python3
"""Auditable, reversible rollout of source-pinned Opik tracing to 14 Hermes profiles.

No production operation occurs by importing this module or running 'status'.
Deploy only after review, with Gateway traffic drained, then restart Gateway and
verify real traced calls. This cannot replace end-to-end functional acceptance.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import uuid

from apply_opik_segmentation import BASE_SHA256, KNOWN_ROLES, transform

RELATIVE_FILE = Path("plugins/opik/lifecycle.py")
JOURNAL_DIR = ".opik-segmentation-rollout"
LOCK_FILE = ".lock"
PATCHED_SHA256 = "a4955c71ab2029065d3751496d864c4d8ae921da3a1f18355ca6adbddc64a638"


class RolloutError(RuntimeError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes, mode: int = 0o644) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".opik-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            os.fchmod(target.fileno(), mode)
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def assert_regular_path(root: Path, path: Path) -> None:
    # Reject symlinks in every component (not just at the final leaf).
    if not root.is_dir() or root.is_symlink():
        raise RolloutError("invalid root")
    rel = path.relative_to(root)
    candidate = root
    for part in rel.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise RolloutError("symlink detected in profile tree")
    if not path.is_file():
        raise RolloutError("missing profile plugin")


def source_paths(root: Path) -> dict[str, Path]:
    return {role: root / "profiles" / role / RELATIVE_FILE
            for role in sorted(KNOWN_ROLES)}


def snapshot(root: Path) -> tuple[dict[str, dict], bytes, bytes]:
    results: dict[str, dict] = {}
    original: bytes | None = None
    first_file: bytes | None = None
    for role, path in source_paths(root).items():
        assert_regular_path(root, path)
        data = path.read_bytes()
        if first_file is None:
            first_file = data
        if digest(data) == BASE_SHA256:
            original = data
        results[role] = {"relative_path": str(path.relative_to(root)),
                         "sha256": digest(data),
                         "mode": path.stat().st_mode & 0o777}
    hashes = {v["sha256"] for v in results.values()}
    if not hashes <= {BASE_SHA256, PATCHED_SHA256}:
        raise RolloutError("profile source drift: refusing partial rollout")
    if original is None:
        # All profiles patched: verify against pinned patched hash rather than
        # trying to re-run the one-time transform on already transformed code.
        if hashes != {PATCHED_SHA256} or first_file is None:
            raise RolloutError("missing canonical pristine or patched source")
        return results, b"", first_file
    modified = transform(original.decode("utf-8")).encode("utf-8")
    if digest(modified) != PATCHED_SHA256:
        raise RolloutError("patched code hash drift")
    return results, original, modified


def status(root: Path) -> dict:
    results, _, modified = snapshot(root)
    patched_sha = digest(modified)
    state = {"pristine": 0, "patched": 0}
    for val in results.values():
        state["patched" if val["sha256"] == patched_sha else "pristine"] += 1
    return {"roles": len(results), **state, "source_sha256": BASE_SHA256,
            "patched_sha256": patched_sha,
            "consistent": (state["pristine"] == len(KNOWN_ROLES)
                           or state["patched"] == len(KNOWN_ROLES))}


def sync_dir(directory: Path) -> None:
    handle = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


def load_manifest(journal: Path, batch_id: str) -> dict:
    if not batch_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in batch_id):
        raise RolloutError("invalid batch id")
    file = journal / batch_id / "manifest.json"
    if not file.is_file():
        raise RolloutError("missing rollback manifest")
    data = json.loads(file.read_text())
    if data.get("version") != 1 or data.get("batch_id") != batch_id:
        raise RolloutError("invalid rollback manifest")
    if set(data.get("roles", {})) != KNOWN_ROLES:
        raise RolloutError("incomplete rollback manifest")
    return data


def rollback(root: Path, journal: Path, batch_id: str) -> dict:
    data = load_manifest(journal, batch_id)
    if data["state"] not in {"applying", "applied", "rolled-back"}:
        raise RolloutError("unexpected rollback state")
    changed = 0
    # Validate every existing file and backup first; then restore.
    restorations = []
    for role, target in source_paths(root).items():
        assert_regular_path(root, target)
        record = data["roles"][role]
        if record["relative_path"] != str(target.relative_to(root)):
            raise RolloutError("manifest path mismatch")
        backup = journal / batch_id / (role + ".bak")
        assert_regular_path(root, backup)
        saved = backup.read_bytes()
        if digest(saved) != record["previous_sha256"]:
            raise RolloutError("backup checksum mismatch")
        current = target.read_bytes()
        if digest(current) not in {record["previous_sha256"], record["patched_sha256"]}:
            raise RolloutError("profile drift since rollout; refusing overwrite")
        restorations.append((target, saved, record["mode"], current != saved))
    for target, saved, mode, different in restorations:
        if different:
            atomic_write(target, saved, mode)
            changed += 1
    data["state"] = "rolled-back"
    atomic_write(journal / batch_id / "manifest.json",
                 json.dumps(data, indent=2, sort_keys=True).encode())
    return {"state": data["state"], "restored": changed, "batch_id": batch_id}


def apply(root: Path, journal: Path) -> dict:
    if journal.is_symlink():
        raise RolloutError("unsafe journal link")
    journal.mkdir(mode=0o700, exist_ok=True)
    metadata, original, patched = snapshot(root)
    if any(record["sha256"] != BASE_SHA256 for record in metadata.values()):
        raise RolloutError("not all profiles are pristine; refusing mixed rollout")
    # One pending journal at a time; failures require explicit reviewed rollback.
    for manifest in journal.glob("*/manifest.json"):
        state = json.loads(manifest.read_text()).get("state")
        if state in {"applying", "applied"}:
            raise RolloutError("existing rollout not finalized; rollback or archive first")
    batch_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    batch = journal / batch_id
    batch.mkdir(mode=0o700)
    patched_hash = digest(patched)
    roles = {}
    for role, target in source_paths(root).items():
        record = metadata[role]
        backup = batch / (role + ".bak")
        atomic_write(backup, original, 0o600)
        roles[role] = {"relative_path": record["relative_path"],
                       "mode": record["mode"],
                       "previous_sha256": BASE_SHA256,
                       "patched_sha256": patched_hash}
    manifest = {"version": 1, "batch_id": batch_id, "state": "applying",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "roles": roles}
    atomic_write(batch / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True).encode(), 0o600)
    sync_dir(batch)
    try:
        for role, target in source_paths(root).items():
            atomic_write(target, patched, roles[role]["mode"])
            if digest(target.read_bytes()) != patched_hash:
                raise RolloutError("patched profile readback mismatch")
        manifest["state"] = "applied"
        atomic_write(batch / "manifest.json",
                     json.dumps(manifest, indent=2, sort_keys=True).encode(), 0o600)
    except Exception:
        # Roll back every role, including a potentially partially-written role.
        rollback(root, journal, batch_id)
        raise
    return {"batch_id": batch_id, "state": "applied",
            "roles_patched": len(roles), "patched_sha256": patched_hash}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "apply", "rollback"))
    parser.add_argument("--root", type=Path, default=Path("/opt/data"))
    parser.add_argument("--batch-id", default="")
    args = parser.parse_args()
    root = args.root.absolute()
    if not root.is_dir() or root.is_symlink():
        raise SystemExit("invalid root")
    if args.action == "status":
        print(json.dumps(status(root), indent=2, sort_keys=True))
        return
    journal = root / JOURNAL_DIR
    if journal.is_symlink():
        raise RolloutError("unsafe journal link")
    journal.mkdir(mode=0o700, exist_ok=True)
    lock_path = journal / LOCK_FILE
    if lock_path.is_symlink():
        raise RolloutError("unsafe lock link")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if args.action == "rollback":
            result = rollback(root, journal, args.batch_id)
        else:
            result = apply(root, journal)
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
