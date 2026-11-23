#!/usr/bin/env python3
"""Project only the read-only GitHub Ops installation grant into its private runtime mount.

The GitHub App private key remains inside Coolify. The temporary installation
grant is minted by the existing Multica refresh service and rotated atomically.
No token is written to stdout or command-line arguments.
"""
import datetime
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

SOURCE = Path("/etc/multica-git-credential/roles/github-ops-reader.json")
TARGET_DIR = Path("/etc/github-ops-mcp/reader")
TARGET = TARGET_DIR / "token.json"
ROLE = "github-ops-reader"
REPOS = {"jtrtdhrst/harness-zar-i-szlif", "jtrtdhrst/zar-i-szlif"}
PERMISSIONS = {"actions": "read", "administration": "read", "contents": "read", "deployments": "read", "metadata": "read"}
WRITER_SOURCE = Path("/etc/multica-git-credential/roles/github-ops-writer.json")
WRITER_TARGET = TARGET_DIR / "writer.json"
WRITER_ROLE = "github-ops-writer"
WRITER_PERMISSIONS = {"actions": "write", "contents": "write", "pull_requests": "write", "metadata": "read"}
NODE_GID = 1000


def check_dir(path, group, mode):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_gid != group or stat.S_IMODE(st.st_mode) != mode:
            raise RuntimeError("Untrusted credential directory")
    finally:
        os.close(fd)


def project(source, target, role, permissions):
    if os.geteuid() != 0:
        raise RuntimeError("Credential projection requires root")
    check_dir(source.parent.parent, 0, 0o700)
    check_dir(source.parent, 0, 0o700)
    check_dir(TARGET_DIR.parent, 0, 0o700)
    check_dir(TARGET_DIR, NODE_GID, 0o750)
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_gid != 0 or st.st_nlink != 1 or stat.S_IMODE(st.st_mode) != 0o600:
        os.close(fd)
        raise RuntimeError("Untrusted source credential")
    with os.fdopen(fd, "r") as f:
        payload = json.load(f)
    if not isinstance(payload, dict) or payload.get("role") != role or payload.get("app_id") != 5398752 or payload.get("installation_id") != 173456397:
        raise RuntimeError("GitHub App grant identity mismatch")
    if set(payload.get("repositories", ())) != REPOS or payload.get("permissions") != permissions:
        raise RuntimeError("GitHub App grant scope mismatch")
    expires = payload.get("expires_at")
    if not isinstance(expires, str) or datetime.datetime.fromisoformat(expires.replace("Z", "+00:00")) <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10):
        raise RuntimeError("GitHub App grant expired")
    token = payload.get("token")
    if not isinstance(token, str) or len(token) < 40 or any(c.isspace() for c in token):
        raise RuntimeError("GitHub App grant invalid")
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".token-", dir=TARGET_DIR)
        os.fchown(fd, 0, NODE_GID)
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, separators=(",", ":"))
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
        tmp = None
    finally:
        if tmp is not None:
            os.unlink(tmp)
    return expires


def main():
    reader_expiry = project(SOURCE, TARGET, ROLE, PERMISSIONS)
    writer_projected = False
    if WRITER_SOURCE.exists():
        project(WRITER_SOURCE, WRITER_TARGET, WRITER_ROLE, WRITER_PERMISSIONS)
        writer_projected = True
    print(json.dumps({"projected": True, "role": ROLE, "expires_at": reader_expiry, "writer_projected": writer_projected}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print('{"projected":false,"error":"projection_denied"}', file=sys.stderr)
        sys.exit(1)

