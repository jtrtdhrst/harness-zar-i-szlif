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
# Existing Coolify named-volume directory mounted read-only at
# /run/secrets/github-ops; preserve the one existing token controller.
WRITER_RUNTIME = Path("/var/lib/docker/volumes/t09dqe2eppn2eiqmhzlf8xzp-bgh-github-app-reader/_data/writer.json")
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


def retire_writer_target(path=None):
    """Revoke an existing projected writer file (system or mounted runtime)."""
    target = path if path is not None else WRITER_TARGET
    try:
        st = os.lstat(target)
    except FileNotFoundError:
        return False
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or
            st.st_gid != NODE_GID or st.st_nlink != 1 or
            stat.S_IMODE(st.st_mode) != 0o640):
        raise RuntimeError("Untrusted projected writer file")
    # Both target directories must be root-owned and not group-writable.
    os.unlink(target)
    return True



def retire_writer_source():
    """Revoke the root-only writer grant when any projection stage fails."""
    try:
        st = os.lstat(WRITER_SOURCE)
    except FileNotFoundError:
        return False
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or
            st.st_gid != 0 or st.st_nlink != 1 or
            stat.S_IMODE(st.st_mode) != 0o600):
        raise RuntimeError("Untrusted source writer grant")
    os.unlink(WRITER_SOURCE)
    return True

def project_writer_runtime():
    """Atomically project validated scoped writer into the existing named volume."""
    check_dir(WRITER_RUNTIME.parent, NODE_GID, 0o750)
    fd = os.open(WRITER_TARGET, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or
                st.st_gid != NODE_GID or st.st_nlink != 1 or
                stat.S_IMODE(st.st_mode) != 0o640 or st.st_size > 16384):
            raise RuntimeError("Untrusted system writer grant")
        with os.fdopen(fd, "rb", closefd=False) as source:
            payload = source.read(16385)
        if len(payload) > 16384:
            raise RuntimeError("Writer grant too large")
        grant = json.loads(payload)
        if (grant.get("role") != WRITER_ROLE or grant.get("app_id") != 5398752 or
                grant.get("installation_id") != 173456397 or
                grant.get("permissions") != WRITER_PERMISSIONS or
                set(grant.get("repositories", ())) != REPOS):
            raise RuntimeError("Runtime writer grant scope mismatch")
    finally:
        os.close(fd)
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".writer-", dir=WRITER_RUNTIME.parent)
        os.fchown(fd, 0, NODE_GID)
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp, WRITER_RUNTIME)
        tmp = None
    finally:
        if tmp is not None:
            os.unlink(tmp)


def main():
    writer_projected = False
    writer_revoked = False
    runtime_revoked = False
    try:
        reader_expiry = project(SOURCE, TARGET, ROLE, PERMISSIONS)
        if WRITER_SOURCE.is_symlink():
            raise RuntimeError("Untrusted writer grant symlink")
        if WRITER_SOURCE.exists():
            project(WRITER_SOURCE, WRITER_TARGET, WRITER_ROLE, WRITER_PERMISSIONS)
            project_writer_runtime()
            writer_projected = True
        else:
            writer_revoked = retire_writer_target()
            runtime_revoked = retire_writer_target(WRITER_RUNTIME)
    except Exception:
        # Any failure in ExecStartPost must also revoke the root source;
        # ExecStart will not run its catch block after it already succeeded.
        cleanup_errors = []
        for cleanup in (lambda: retire_writer_target(WRITER_TARGET),
                        lambda: retire_writer_target(WRITER_RUNTIME),
                        retire_writer_source):
            try:
                cleanup()
            except Exception as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            raise RuntimeError("Writer revocation incomplete") from cleanup_errors[0]
        raise
    print(json.dumps({"projected": True, "role": ROLE, "expires_at": reader_expiry,
                      "writer_projected": writer_projected, "writer_revoked": writer_revoked,
                      "runtime_writer_revoked": runtime_revoked}))

if __name__ == "__main__":
    try:
        main()
    except Exception:
        print('{"projected":false,"error":"projection_denied"}', file=sys.stderr)
        sys.exit(1)

