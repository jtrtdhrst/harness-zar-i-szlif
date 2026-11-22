#!/usr/bin/env python3
"""Read-only source/projection preflight for the existing GitHub Ops MCP runtime.

Compares versioned refresher/projector source against the actual files loaded by
systemd. Reports credential presence and filesystem safety, never token values.
Does not mint tokens, modify services, change Coolify, or authorize releases.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

FILES = ("multica-zar-github-app-refresh.py", "github-ops-token-project.py")
DEFAULT_INSTALLED = Path("/usr/local/libexec")
WRITER_ROLE = Path("/etc/multica-git-credential/roles/github-ops-writer.json")
WRITER_PROJECTION = Path("/etc/github-ops-mcp/reader/writer.json")
WRITER_VOLUME = Path("/var/lib/docker/volumes/t09dqe2eppn2eiqmhzlf8xzp-bgh-github-app-reader/_data/writer.json")


def source_digest(path):
    try:
        entry = os.lstat(path)
    except FileNotFoundError:
        return ("MISSING", None)
    if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1 or entry.st_size > 1024 * 1024:
        return ("UNTRUSTED", None)
    with open(path, "rb") as stream:
        return ("FILE", hashlib.sha256(stream.read()).hexdigest())


def inspect_writer(path, *, gid=None, mode=0o600):
    # Stat-only: credential content is never opened by this diagnostic.
    try:
        entry = os.lstat(path)
    except FileNotFoundError:
        return "MISSING"
    if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != 0 or
            (gid is not None and entry.st_gid != gid) or
            stat.S_IMODE(entry.st_mode) != mode or entry.st_nlink != 1):
        return "UNTRUSTED"
    return "PRESENT"


def evaluate(source_dir, installed_dir, role_path, projected_path, volume_path):
    source = {}
    for filename in FILES:
        trusted, want = source_digest(source_dir / filename)
        installed, actual = source_digest(installed_dir / filename)
        source[filename] = (
            "MATCH" if trusted == installed == "FILE" and want == actual
            else "UNTRUSTED" if "UNTRUSTED" in (trusted, installed)
            else "MISSING" if "MISSING" in (trusted, installed)
            else "DRIFT"
        )
    credentials = {
        "writer_role": inspect_writer(role_path),
        "writer_projection": inspect_writer(projected_path, gid=1000, mode=0o640),
        "writer_runtime_volume": inspect_writer(volume_path, gid=1000, mode=0o640),
    }
    return {
        "source": source,
        "writer_files": credentials,
        "runtime_source_current": all(value == "MATCH" for value in source.values()),
        "writer_files_present": all(value == "PRESENT" for value in credentials.values()),
        "note": "Read-only preflight; source parity and file presence do not authorize writes or prove live production E2E",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--installed-dir", type=Path, default=DEFAULT_INSTALLED)
    parser.add_argument("--writer-role-path", type=Path, default=WRITER_ROLE)
    parser.add_argument("--writer-projection-path", type=Path, default=WRITER_PROJECTION)
    parser.add_argument("--writer-volume-path", type=Path, default=WRITER_VOLUME)
    parser.add_argument("--require-writer", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate(args.source_dir, args.installed_dir, args.writer_role_path,
                      args.writer_projection_path, args.writer_volume_path)
    print(json.dumps(result, sort_keys=True))
    if not result["runtime_source_current"]:
        return 2
    if args.require_writer and not result["writer_files_present"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
