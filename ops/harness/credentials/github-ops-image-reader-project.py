#!/usr/bin/env python3
"""Atomically project one dedicated GitHub App reader grant into an isolated Coolify volume.

Input is the existing native Multica GitHub App refresh output. This projector
never mints or broadens credentials; it only verifies and copies an exact-scope
installation token to a Docker volume belonging to ONE app. The App private key
never leaves Coolify, and no token is printed or passed on an argv.
"""
import datetime
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

SOURCE = Path("/etc/multica-git-credential/roles/github-ops-reader-harness.json")
ROLE = "github-ops-reader-harness"
REPOS = ["jtrtdhrst/harness-zar-i-szlif"]
PERMISSIONS = {"contents": "read", "metadata": "read"}
APP_ID = 5398752
INSTALLATION_ID = 173456397
NODE_GID = 1000
DESTINATION = "/run/secrets/github-ops"


def read_exact_grant(path=SOURCE):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    with os.fdopen(fd, "r", encoding="utf-8") as file:
        st = os.fstat(file.fileno())
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_gid != 0
                or st.st_nlink != 1 or stat.S_IMODE(st.st_mode) != 0o600):
            raise RuntimeError("Untrusted token source")
        data = json.load(file)
    return validate_grant(data)


def validate_grant(data, now=None):
    if (not isinstance(data, dict) or data.get("role") != ROLE
            or data.get("app_id") != APP_ID or data.get("installation_id") != INSTALLATION_ID
            or data.get("repositories") != REPOS or data.get("permissions") != PERMISSIONS):
        raise RuntimeError("GitHub token scope mismatch")
    token = data.get("token")
    if not isinstance(token, str) or len(token) < 40 or any(c.isspace() for c in token):
        raise RuntimeError("Invalid GitHub token")
    expires_at = data.get("expires_at")
    if not isinstance(expires_at, str):
        raise RuntimeError("Token expiry missing")
    expiry = datetime.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if not now + datetime.timedelta(minutes=10) < expiry <= now + datetime.timedelta(hours=1):
        raise RuntimeError("Token expiry outside permitted window")
    return data


def docker_json(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True,
                            timeout=15, check=False)
    if result.returncode != 0:
        raise RuntimeError("Docker readback failed")
    return json.loads(result.stdout)


def validated_volume(app_uuid, volume_name):
    if not re.fullmatch(r"[a-z0-9]{24}", app_uuid):
        raise RuntimeError("Invalid Coolify UUID")
    if not re.fullmatch(re.escape(app_uuid) + r"-[a-z0-9-]{8,80}", volume_name):
        raise RuntimeError("Volume name outside app UUID")
    volumes = docker_json("volume", "inspect", volume_name)
    if len(volumes) != 1 or volumes[0].get("Name") != volume_name:
        raise RuntimeError("Unexpected Docker volume")
    directory = Path(volumes[0]["Mountpoint"])
    stat_info = os.lstat(directory)
    if (not stat.S_ISDIR(stat_info.st_mode) or stat_info.st_uid != 0
            or stat.S_IMODE(stat_info.st_mode) & 0o002):
        raise RuntimeError("Untrusted volume root")
    container_ids = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "volume=" + volume_name],
        capture_output=True, text=True, timeout=15, check=False)
    if container_ids.returncode != 0 or not container_ids.stdout.strip():
        raise RuntimeError("Volume not mounted by Coolify app")
    attached = docker_json("inspect", *container_ids.stdout.split())
    for container in attached:
        labels = (container.get("Config") or {}).get("Labels") or {}
        if labels.get("coolify.applicationUuid") != app_uuid:
            raise RuntimeError("Volume exposed to a different application")
        mounts = container.get("Mounts") or []
        if not any(m.get("Type") == "volume" and m.get("Name") == volume_name
                   and m.get("Destination") == DESTINATION for m in mounts):
            raise RuntimeError("Unexpected token volume destination")
    return directory


def project(data, directory):
    if os.geteuid() != 0:
        raise RuntimeError("Root required")
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    temp = None
    try:
        st = os.fstat(fd)
        if st.st_uid != 0 or stat.S_IMODE(st.st_mode) & 0o002:
            raise RuntimeError("Unsafe destination directory")
        target_fd, temp = tempfile.mkstemp(prefix=".token-", dir=directory)
        os.fchown(target_fd, 0, NODE_GID)
        os.fchmod(target_fd, 0o640)
        with os.fdopen(target_fd, "w", encoding="utf-8") as out:
            json.dump(data, out, separators=(",", ":"))
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, directory / "token.json")
        temp = None
        os.fsync(fd)
    finally:
        os.close(fd)
        if temp is not None:
            os.unlink(temp)


def main():
    app_uuid = os.environ.get("GITHUB_OPS_IMAGE_APP_UUID", "")
    volume_name = os.environ.get("GITHUB_OPS_IMAGE_READER_VOLUME", "")
    directory = validated_volume(app_uuid, volume_name)
    data = read_exact_grant()
    project(data, directory)
    print(json.dumps({"projected": True, "app_uuid": app_uuid, "role": ROLE,
                      "expires_at": data["expires_at"]}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print('{"projected":false,"error":"scope_or_destination_denied"}', file=sys.stderr)
        sys.exit(1)
