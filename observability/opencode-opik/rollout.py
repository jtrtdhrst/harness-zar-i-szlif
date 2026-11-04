#!/usr/bin/env python3
"""Source-pinned, reversible OpenCode -> Opik plugin promotion.

No live changes on import or status. Apply/rollback require an externally
verified drain of Paperclip agent runs, independent review and release approval.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
import uuid

BASELINE_SHA = "3331ab8310a08448dd40cae8bcda0ee7fa9a299fcaa817db58e82007134839f6"
CANDIDATE_SHA = "f3509d91bf6c5f5d8d23c7221767cd3fbbe53b83c4669acc9cf99665d5565f49"
DEFAULT_TARGET = Path("/paperclip/.config/opencode/opik-observability/index.mjs")
JOURNAL_NAME = ".opik-observability-rollout"

class RolloutError(RuntimeError):
    pass

def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def assert_regular(path: Path) -> None:
    if not path.is_absolute():
        raise RolloutError("absolute path required")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise RolloutError("symlink path refused")
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise RolloutError("regular file required")

def atomic_write(path: Path, content: bytes, mode: int, owner: tuple[int, int] | None = None) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".opik-atomic-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            os.fchmod(out.fileno(), mode)
            if owner is not None and os.geteuid() == 0:
                os.fchown(out.fileno(), *owner)
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def candidate_bytes(source: Path) -> bytes:
    assert_regular(source)
    content = source.read_bytes()
    if digest(content) != CANDIDATE_SHA:
        raise RolloutError("candidate source SHA mismatch")
    return content

def status(target: Path, source: Path) -> dict:
    assert_regular(target)
    candidate_bytes(source)
    current = digest(target.read_bytes())
    state = "pristine" if current == BASELINE_SHA else (
        "candidate" if current == CANDIDATE_SHA else "drift")
    return {"state": state, "target_sha256": current,
            "baseline_sha256": BASELINE_SHA, "candidate_sha256": CANDIDATE_SHA,
            "release_admission": "not_verified_by_status"}

def journal_dir(target: Path, create: bool) -> Path:
    journal = target.parent / JOURNAL_NAME
    if journal.is_symlink():
        raise RolloutError("journal symlink refused")
    if create and not journal.exists():
        journal.mkdir(mode=0o700)
    if journal.exists():
        if not journal.is_dir() or (journal.stat().st_mode & 0o777) != 0o700:
            raise RolloutError("journal directory must be private 0700")
    return journal

def write_manifest(path: Path, document: dict) -> None:
    atomic_write(path, json.dumps(document, indent=2, sort_keys=True).encode(), 0o600)

def acquire_lock(journal: Path):
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(journal / ".lock", flags, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd

def apply(target: Path, source: Path, drained: bool) -> dict:
    if not drained:
        raise RolloutError("externally verified agent drain required")
    assert_regular(target)
    candidate = candidate_bytes(source)
    journal = journal_dir(target, create=True)
    fd = acquire_lock(journal)
    try:
        current = target.read_bytes()
        existing = digest(current)
        if existing == CANDIDATE_SHA:
            return {"state": "already_applied", "sha256": existing}
        if existing != BASELINE_SHA:
            raise RolloutError("production source drift; refusing overwrite")
        for file in journal.glob("*/manifest.json"):
            if file.is_symlink():
                raise RolloutError("manifest symlink refused")
            if json.loads(file.read_text()).get("state") in ("applying", "applied"):
                raise RolloutError("outstanding rollout journal must be rolled back")
        old_stat = target.stat()
        mode, owner = stat.S_IMODE(old_stat.st_mode), (old_stat.st_uid, old_stat.st_gid)
        batch_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:10]
        batch = journal / batch_id
        batch.mkdir(mode=0o700)
        backup = batch / "original.mjs"
        atomic_write(backup, current, 0o600)
        manifest = {"version": 1, "batch_id": batch_id, "state": "applying",
                    "original_sha256": BASELINE_SHA, "candidate_sha256": CANDIDATE_SHA,
                    "mode": mode, "uid": owner[0], "gid": owner[1]}
        mf = batch / "manifest.json"
        write_manifest(mf, manifest)
        try:
            if digest(target.read_bytes()) != BASELINE_SHA:
                raise RolloutError("source changed during admission")
            atomic_write(target, candidate, mode, owner)
            if digest(target.read_bytes()) != CANDIDATE_SHA:
                raise RolloutError("candidate readback mismatch")
            manifest["state"] = "applied"
            write_manifest(mf, manifest)
        except Exception:
            if digest(target.read_bytes()) == CANDIDATE_SHA:
                atomic_write(target, current, mode, owner)
                manifest["state"] = "rolled_back"
                write_manifest(mf, manifest)
            raise
        return {"state": "applied", "batch_id": batch_id, "sha256": CANDIDATE_SHA}
    finally:
        os.close(fd)

def rollback(target: Path, source: Path, batch_id: str, drained: bool) -> dict:
    if not drained:
        raise RolloutError("externally verified agent drain required")
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{10}", batch_id):
        raise RolloutError("invalid batch id")
    assert_regular(target)
    candidate_bytes(source)
    journal = journal_dir(target, create=False)
    if not journal.exists():
        raise RolloutError("rollback journal missing")
    fd = acquire_lock(journal)
    try:
        manifest_file = journal / batch_id / "manifest.json"
        backup_file = journal / batch_id / "original.mjs"
        assert_regular(manifest_file)
        assert_regular(backup_file)
        manifest = json.loads(manifest_file.read_text())
        if manifest.get("version") != 1 or manifest.get("batch_id") != batch_id:
            raise RolloutError("rollback manifest mismatch")
        if manifest.get("original_sha256") != BASELINE_SHA or manifest.get("candidate_sha256") != CANDIDATE_SHA:
            raise RolloutError("rollback manifest hash mismatch")
        saved = backup_file.read_bytes()
        if digest(saved) != BASELINE_SHA:
            raise RolloutError("rollback backup corrupt")
        current = digest(target.read_bytes())
        if current not in (BASELINE_SHA, CANDIDATE_SHA):
            raise RolloutError("target drift since rollout")
        if current == CANDIDATE_SHA:
            atomic_write(target, saved, manifest["mode"], (manifest["uid"], manifest["gid"]))
        if digest(target.read_bytes()) != BASELINE_SHA:
            raise RolloutError("rollback readback mismatch")
        manifest["state"] = "rolled_back"
        write_manifest(manifest_file, manifest)
        return {"state": "rolled_back", "batch_id": batch_id, "sha256": BASELINE_SHA}
    finally:
        os.close(fd)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "apply", "rollback"))
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--drained", action="store_true",
                        help="assert externally proven no-live-agent-runs release gate")
    args = parser.parse_args()
    target = args.target.absolute()
    source = (Path(__file__).parent / "index.mjs").absolute()
    if args.action == "status":
        result = status(target, source)
    elif args.action == "apply":
        result = apply(target, source, args.drained)
    else:
        result = rollback(target, source, args.batch_id, args.drained)
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    main()
