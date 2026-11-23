#!/usr/bin/env python3
"""Versioned, fail-closed ArkCodexImageGen compatibility overlay (KOMAA-1599)."""
import argparse
import ast
import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile

EXPECTED_ORIGINAL_SHA = "5b869128443d88a7eb8f874a2a2cc6fca81269b92fdc82b50e55380497108bdf"
DEFAULT_TARGET = Path("/app/custom_nodes/comfyui-arkennemasis/codex_provider/nodes.py")
DEFAULT_BACKUP = Path("/app/user/.arkcodex-compat/KOMAA-1599/nodes.py.original")

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def fixed_bytes(source: bytes) -> bytes:
    if sha(source) != EXPECTED_ORIGINAL_SHA:
        raise ValueError("Refusing unknown original nodes.py digest")
    if b'IMAGE_MODEL = "gpt-image-2.5"' not in source:
        raise ValueError("Pinned image model is not present")
    eol = b"\r\n" if b"\r\n" in source else b"\n"
    unwanted = [
        b'HOST_EFFORT = "low"' + eol,
        b'            "reasoning": {"effort": HOST_EFFORT},' + eol,
    ]
    for line in unwanted:
        if source.count(line) != 1:
            raise ValueError("Source layout differs from independently verified snapshot")
        source = source.replace(line, b"", 1)
    ast.parse(source.decode("utf-8"))
    if b"HOST_EFFORT" in source:
        raise ValueError("Image effort reference remains")
    return source

def atomic_write(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".komaa1599-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def execute(target: Path, backup: Path, action: str) -> str:
    if not target.is_file() or target.is_symlink() or backup.is_symlink():
        raise ValueError("Missing or symlinked source/backup")
    current = target.read_bytes()
    original = backup.read_bytes() if backup.exists() else None
    if original is not None and sha(original) != EXPECTED_ORIGINAL_SHA:
        raise ValueError("Backup does not match original digest")
    if original is None and sha(current) != EXPECTED_ORIGINAL_SHA:
        raise ValueError("Unknown source and no trusted rollback backup")
    expected = fixed_bytes(original if original is not None else current)
    mode = stat.S_IMODE(target.stat().st_mode)
    current_sha = sha(current)
    patched_sha = sha(expected)

    if current_sha not in (EXPECTED_ORIGINAL_SHA, patched_sha):
        raise ValueError("Unexpected live nodes.py; no mutation allowed")

    if action == "check":
        return "PATCHED" if current_sha == patched_sha else "PATCHABLE"
    if action == "rollback":
        if current_sha == EXPECTED_ORIGINAL_SHA:
            return "ALREADY_ORIGINAL"
        if original is None:
            raise ValueError("No trusted original backup for rollback")
        atomic_write(target, original, mode)
        return "ROLLED_BACK"

    if current_sha == patched_sha:
        return "ALREADY_PATCHED"
    if original is None:
        atomic_write(backup, current, 0o600)
    atomic_write(target, expected, mode)
    if sha(target.read_bytes()) != patched_sha:
        raise ValueError("Post-write digest mismatch")
    return "PATCHED"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["check", "apply", "rollback"])
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    args = parser.parse_args()
    try:
        result = execute(args.target, args.backup, args.action)
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"KOMAA-1599 FAIL CLOSED: {exc}", file=sys.stderr)
        return 2
    print(f"KOMAA-1599 {result}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
