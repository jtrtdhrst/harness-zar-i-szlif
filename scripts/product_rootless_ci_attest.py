#!/usr/bin/env python3
"""Root-controlled, credential-free Product CI at exact GitHub source tree.

The root process ONLY downloads, validates and freezes source, starts an
unprivileged rootless-Docker build, and signs the result. It never executes
npm, git hooks, Docker or PR-supplied shell code as root.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import io
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request

REPO = "miloszspyrka-code/zar-i-szlif"
GUEST = "zis-ci-guest"
ROOT = Path("/var/lib/zis-ci-source")
LOG_ROOT = Path("/var/lib/paperclip-gitops/product-rootless-ci-logs")
RECEIPTS = Path("/var/lib/paperclip-gitops/local-ci")
KEY = Path("/etc/paperclip-gitops/product-rootless-ci-signing.key")
TOKEN = Path("/etc/multica-git-credential/roles/release.json")
DOCKER_SOCKET = Path("/run/zis-ci-guest/docker.sock")
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_TARBALL = 64 * 1024 * 1024
MAX_EXPANDED = 384 * 1024 * 1024

class Refused(Exception):
    pass

def require_sha(value: str) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise Refused("invalid_source_sha")
    return value

def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

def sign(receipt: dict, key: bytes) -> str:
    if len(key) != 32:
        raise Refused("invalid_signing_key")
    return hmac.new(key, canonical(receipt), hashlib.sha256).hexdigest()

def verify(receipt: dict, key: bytes) -> bool:
    if not isinstance(receipt, dict):
        return False
    x = receipt.copy()
    signature = x.pop("signature", None)
    return isinstance(signature, str) and hmac.compare_digest(sign(x, key), signature)

def guest_uid() -> int:
    return pwd.getpwnam(GUEST).pw_uid

def preflight() -> int:
    if os.geteuid() != 0:
        raise Refused("root_operator_required")
    uid = guest_uid()
    if uid == 0:
        raise Refused("guest_must_be_nonroot")
    s = DOCKER_SOCKET.stat()
    if not stat.S_ISSOCK(s.st_mode) or s.st_uid != uid or s.st_mode & 0o007:
        raise Refused("dedicated_rootless_socket_untrusted")
    return uid

def github_request(path: str, *, accept: str = "application/vnd.github+json") -> bytes:
    data = json.loads(TOKEN.read_text(encoding="utf8"))
    token = data.get("token", "")
    if not isinstance(token, str) or not token:
        raise Refused("github_app_installation_token_missing")
    req = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + "/" + path,
        headers={"Authorization": "Bearer " + token, "Accept": accept,
                 "User-Agent": "ZariRootlessProductCI/1"})
    with urllib.request.urlopen(req, timeout=90) as response:
        value = response.read(MAX_TARBALL + 1)
    if len(value) > MAX_TARBALL:
        raise Refused("oversized_github_response")
    return value

def github_snapshot(sha: str) -> tuple[str, bytes]:
    meta = json.loads(github_request("git/commits/" + sha))
    if meta.get("sha") != sha:
        raise Refused("github_commit_sha_mismatch")
    tree = (meta.get("tree") or {}).get("sha")
    require_sha(tree)
    data = github_request("tarball/" + sha, accept="application/vnd.github+json")
    return tree, data

def validated_members(archive: tarfile.TarFile) -> str:
    total, prefix, n = 0, None, 0
    for member in archive:
        n += 1
        if n > 50000 or not (member.isfile() or member.isdir()):
            raise Refused("tar_member_type_not_allowed")
        if member.size < 0:
            raise Refused("invalid_tar_member")
        total += member.size
        if total > MAX_EXPANDED:
            raise Refused("expanded_tree_too_large")
        parts = PurePosixPath(member.name).parts
        if (not parts or member.name.startswith("/") or "\\" in member.name
                or any(part in ("", ".", "..") for part in parts)):
            raise Refused("unsafe_tar_path")
        if prefix is None:
            prefix = parts[0]
        elif parts[0] != prefix:
            raise Refused("mixed_tar_roots")
    if prefix is None or n < 2:
        raise Refused("empty_github_archive")
    return prefix

def command(*argv: str, cwd: Path, timeout: int = 90) -> str:
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                       text=True, timeout=timeout)
    if p.returncode:
        raise Refused("source_tree_command_failed")
    return p.stdout.strip()

def freeze_tree(source: Path, uid: int) -> None:
    import grp
    gid = pwd.getpwnam(GUEST).pw_gid
    for here, directories, files in os.walk(source, topdown=True, followlinks=False):
        for entry in directories + files:
            target = Path(here) / entry
            if target.is_symlink():
                raise Refused("source_symlinks_not_allowed")
            os.chown(target, 0, gid, follow_symlinks=False)
            if target.is_dir():
                target.chmod(0o750)
            elif target.is_file():
                mode = target.stat().st_mode
                target.chmod(0o750 if mode & 0o111 else 0o640)
            else:
                raise Refused("unsupported_source_node")
    os.chown(source, 0, gid)
    source.chmod(0o750)

def prepare_source(sha: str, expected_tree: str, tgz: bytes, uid: int) -> Path:
    gid = pwd.getpwnam(GUEST).pw_gid
    ROOT.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(ROOT, 0, gid)
    ROOT.chmod(0o750)
    final = ROOT / sha
    if final.exists():
        actual = command("git", "-C", str(final), "write-tree", cwd=final)
        if actual != expected_tree or final.stat().st_uid != 0:
            raise Refused("existing_source_snapshot_untrusted")
        return final
    with tempfile.TemporaryDirectory(prefix="incoming-", dir=ROOT) as temp:
        base = Path(temp)
        with tarfile.open(fileobj=io.BytesIO(tgz), mode="r:gz") as archive:
            prefix = validated_members(archive)
            archive.extractall(base, filter="data")
        source = base / prefix
        if not source.is_dir():
            raise Refused("archive_root_unavailable")
        command("git", "init", "-q", cwd=source)
        command("git", "add", "-f", "-A", cwd=source)
        actual = command("git", "write-tree", cwd=source)
        if actual != expected_tree:
            raise Refused("source_tree_sha_mismatch")
        freeze_tree(source, uid)
        source.rename(final)
    return final

def guest_ci(source: Path, sha: str) -> str:
    LOG_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    LOG_ROOT.chmod(0o700)
    log = LOG_ROOT / (sha + ".log")
    shell = r'''
set -eu
test "$(git -c safe.directory="$(pwd)" cat-file -t EXPECTED_TREE)" = tree
test ! -r /opt/zis-actions-runner/.credentials
test ! -r /srv/multica-zar/.hermes/auth.json
test ! -r /etc/multica-git-credential/roles/release.json
test ! -w /run/docker.sock
test ! -w /run/zis-rootless-docker/docker.sock
docker info --format '{{json .SecurityOptions}}' | grep -q rootless
docker build --progress=plain --file ops/coolify/Dockerfile --target build --tag product-ci:build .
docker build --progress=plain --file ops/coolify/Dockerfile.ci --tag product-ci:validation .
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --memory 5g --env npm_config_offline=true product-ci:validation sh -c 'npm run validate:code'
docker build --progress=plain --file ops/coolify/Dockerfile --tag product-ci:verified .
name=zis-ci-release-EXPECTED_SHORT
negative=$(mktemp)
trap 'docker rm -f "$name" >/dev/null 2>&1 || true; rm -f "$negative"' EXIT
docker run -d --name "$name" --network none --cap-drop ALL --security-opt no-new-privileges -e SOURCE_COMMIT=EXPECTED_SHA product-ci:verified >/dev/null
docker exec "$name" cat /usr/share/nginx/html/__release.json | python3 -c 'import sys,json; x=json.load(sys.stdin); assert x["commit"]=="EXPECTED_SHA" and x["source"]=="zar-i-szlif/main"'
docker rm -f "$name" >/dev/null
if docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges product-ci:verified >"$negative" 2>&1; then
    echo NEGATIVE_VERSIONLESS_ALLOWED
    exit 89
fi
grep -q 'release provenance unavailable' "$negative"
echo ROOTLESS_EXACT_SOURCE_BUILD_AND_TEST_PASS
'''.replace("EXPECTED_TREE", command("git", "write-tree", cwd=source)).replace("EXPECTED_SHA", sha).replace("EXPECTED_SHORT", sha[:12])
    env = ["HOME=/var/lib/zis-ci-guest",
           "DOCKER_HOST=unix:///run/zis-ci-guest/docker.sock",
           "PYTHONDONTWRITEBYTECODE=1"]
    argv = ["/usr/sbin/runuser", "-u", GUEST, "--", "env", *env, "/bin/sh", "-c", shell]
    with open(log, "wb") as output:
        try:
            p = subprocess.run(argv, cwd=source, stdout=output, stderr=subprocess.STDOUT,
                               timeout=1800, env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"})
        except subprocess.TimeoutExpired as exc:
            raise Refused("rootless_ci_timeout") from exc
    if p.returncode:
        raise Refused("rootless_ci_failed")
    if "ROOTLESS_EXACT_SOURCE_BUILD_AND_TEST_PASS" not in log.read_text(errors="replace"):
        raise Refused("ci_milestone_unobserved")
    return hashlib.sha256(log.read_bytes()).hexdigest()

def receipt_key() -> bytes:
    KEY.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not KEY.exists():
        fd = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, os.urandom(32))
        finally:
            os.close(fd)
    st = KEY.stat()
    if st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o600 or not stat.S_ISREG(st.st_mode):
        raise Refused("attestation_key_not_private")
    key = KEY.read_bytes()
    if len(key) != 32:
        raise Refused("attestation_key_invalid")
    return key

def store_receipt(payload: dict, key: bytes) -> Path:
    RECEIPTS.mkdir(mode=0o700, parents=True, exist_ok=True)
    name = RECEIPTS / (payload["sha"] + ".json")
    record = dict(payload, signature=sign(payload, key))
    tmp = name.with_suffix(".new")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(canonical(record) + b"\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, name)
    finally:
        if tmp.exists():
            tmp.unlink()
    return name

def store_premerge_receipt(payload: dict) -> Path:
    """Compatibility with already deployed native Product promotion controller.

    The root-owned file is written only after the same successful immutable
    source build+offline tests+positive/negative runtime canaries as the
    signed audit receipt. This does not alter ci-approved or Coolify.
    """
    name = RECEIPTS / ("premerge-" + payload["sha"] + ".json")
    record = {
        "schema_version": 2, "sha": payload["sha"], "tree": payload["tree"],
        "runner": "zis-rootless-exact-tree",
        "source": "root-verified-systemd-e2e",
        "exit_code": 0, "verified_at": payload["verified_at"],
        "stages": {
            "exact_tree": True, "rootless_isolation": True,
            "full_product_build": True, "network_none_validation": True,
            "final_image": True, "positive_provenance": True,
            "negative_versionless": True,
        },
    }
    tmp = name.with_suffix(".new")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(canonical(record) + b"\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, name)
    finally:
        if tmp.exists():
            tmp.unlink()
    return name

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    sha = require_sha(args.sha)
    uid = preflight()
    if args.plan:
        print(json.dumps({"result": "ready_to_attempt", "source": sha,
                          "isolated_uid": uid, "production_deploy": False}))
        return 0
    lock = Path("/var/lib/paperclip-gitops/rootless-ci.lock")
    with lock.open("a+", encoding="utf8") as locked:
        try:
            fcntl.flock(locked.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refused("rootless_ci_already_running") from exc
        tree, tar = github_snapshot(sha)
        source = prepare_source(sha, tree, tar, uid)
        log_sha = guest_ci(source, sha)
        payload = {"schema_version": 2, "sha": sha, "tree": tree,
                   "runner": "zis-ci-guest-rootless", "runner_uid": uid,
                   "command": "docker build && npm run validate:code (network none) && docker build",
                   "exit_code": 0, "log_sha256": log_sha,
                   "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        path = store_receipt(payload, receipt_key())
        premerge = store_premerge_receipt(payload)
    print(json.dumps({"result": "attested", "sha": sha, "tree": tree,
                      "runner_uid": uid, "receipt": str(path),
                      "premerge_receipt": str(premerge)}, sort_keys=True))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Refused, OSError, ValueError, TimeoutError) as exc:
        print(json.dumps({"result": "denied", "reason": str(exc) if isinstance(exc, Refused) else "attester_io_failure"}))
        raise SystemExit(78)
