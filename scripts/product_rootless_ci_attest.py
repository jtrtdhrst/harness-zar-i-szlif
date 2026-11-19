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
MAX_LOG_BYTES = 32 * 1024 * 1024
MAX_DAEMON_MEMORY = 6 * 1024 * 1024 * 1024
MAX_DAEMON_TASKS = 256
MAX_DAEMON_CPU_SECONDS = 2.0

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
    parent = DOCKER_SOCKET.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != uid
            or stat.S_IMODE(parent.st_mode) != 0o700):
        raise Refused("dedicated_rootless_socket_directory_untrusted")
    s = DOCKER_SOCKET.lstat()  # never follow a symlink to some other daemon
    if not stat.S_ISSOCK(s.st_mode) or s.st_uid != uid or stat.S_IMODE(s.st_mode) != 0o600:
        raise Refused("dedicated_rootless_socket_untrusted")
    daemon_budget_preflight()
    return uid

def daemon_budget_preflight() -> None:
    """Require a dedicated, bounded cgroup for Docker builds; unknown = deny."""
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", "show", "zis-ci-guest-docker.service",
             "-p", "User", "-p", "MemoryMax", "-p", "TasksMax",
             "-p", "CPUQuotaPerSecUSec", "-p", "ActiveState",
             "-p", "ControlGroup", "-p", "MainPID", "--no-pager"],
            check=True, capture_output=True, text=True, timeout=6)
        fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        memory = int(fields["MemoryMax"])
        tasks = int(fields["TasksMax"])
        quota = fields["CPUQuotaPerSecUSec"]
        if not quota.endswith("s"):
            raise ValueError("CPU quota unit")
        cpu_seconds = float(quota[:-1])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError, KeyError) as exc:
        raise Refused("rootless_daemon_budget_unverified") from exc
    if (fields.get("User") != GUEST or fields.get("ActiveState") != "active"
            or not 0 < memory <= MAX_DAEMON_MEMORY
            or not 0 < tasks <= MAX_DAEMON_TASKS
            or not 0 < cpu_seconds <= MAX_DAEMON_CPU_SECONDS
            or fields.get("ControlGroup") != "/system.slice/zis-ci-guest-docker.service"):
        raise Refused("rootless_daemon_budget_untrusted")
    try:
        main_pid = int(fields["MainPID"])
        if main_pid <= 1:
            raise ValueError("invalid daemon pid")
        expected_cgroup = "0::" + fields["ControlGroup"]
        if expected_cgroup not in Path("/proc", str(main_pid), "cgroup").read_text().splitlines():
            raise Refused("rootless_daemon_main_cgroup_untrusted")
        socket = subprocess.run(["/usr/bin/ss", "-H", "-x", "-l", "-n", "-p"],
                                check=True, capture_output=True, text=True, timeout=6)
        matching = [line for line in socket.stdout.splitlines()
                    if re.search(r"(?<!\\S)" + re.escape(str(DOCKER_SOCKET)) + r"(?=\\s)", line)]
        if len(matching) != 1:
            raise Refused("rootless_socket_listener_unverified")
        owners = re.findall(r'\\("dockerd",pid=(\\d+),fd=\\d+\\)', matching[0])
        if len(owners) != 1:
            raise Refused("rootless_socket_daemon_unverified")
        daemon_pid = int(owners[0])
        if os.stat("/proc/" + str(daemon_pid)).st_uid != guest_uid():
            raise Refused("rootless_socket_owner_untrusted")
        if expected_cgroup not in Path("/proc", str(daemon_pid), "cgroup").read_text().splitlines():
            raise Refused("rootless_socket_cgroup_untrusted")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        raise Refused("rootless_socket_daemon_binding_unverified") from exc


def private_github_token() -> str:
    """Open trusted role-credential inode once, using openat + O_NOFOLLOW."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        directory_fd = os.open(TOKEN.parent, flags | os.O_DIRECTORY)
    except OSError as exc:
        raise Refused("github_token_directory_unavailable") from exc
    try:
        parent = os.fstat(directory_fd)
        if (parent.st_uid != os.geteuid() or not stat.S_ISDIR(parent.st_mode)
                or (stat.S_IMODE(parent.st_mode) & 0o022)):
            raise Refused("github_token_directory_untrusted")
        try:
            key_fd = os.open(TOKEN.name, flags, dir_fd=directory_fd)
        except OSError as exc:
            raise Refused("github_token_file_unavailable") from exc
        try:
            st = os.fstat(key_fd)
            if (st.st_uid != os.geteuid() or not stat.S_ISREG(st.st_mode)
                    or stat.S_IMODE(st.st_mode) != 0o600
                    or st.st_nlink != 1 or st.st_size > 8192):
                raise Refused("github_token_file_untrusted")
            raw = os.read(key_fd, 8193)
            if len(raw) > 8192:
                raise Refused("github_token_file_oversized")
        finally:
            os.close(key_fd)
    finally:
        os.close(directory_fd)
    try:
        data = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise Refused("github_token_file_invalid") from exc
    token = data.get("token") if isinstance(data, dict) else None
    if not isinstance(token, str) or not token:
        raise Refused("github_app_installation_token_missing")
    return token


def github_request(path: str, *, accept: str = "application/vnd.github+json") -> bytes:
    token = private_github_token()
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

def isolated_guest_environment() -> tuple[Path, list[str]]:
    """Create a new credential-empty Docker client identity for each CI run."""
    guest = pwd.getpwnam(GUEST)
    home = Path(tempfile.mkdtemp(prefix="zari-product-ci-home-", dir="/var/tmp"))
    try:
        os.chown(home, guest.pw_uid, guest.pw_gid)
        home.chmod(0o700)
        config = home / ".docker"
        config.mkdir(mode=0o700)
        os.chown(config, guest.pw_uid, guest.pw_gid)
        return home, ["HOME=" + str(home), "DOCKER_CONFIG=" + str(config),
                      "DOCKER_HOST=unix:///run/zis-ci-guest/docker.sock",
                      "PYTHONDONTWRITEBYTECODE=1"]
    except Exception:
        shutil.rmtree(home, ignore_errors=True)
        raise


def fsync_directory(path: Path) -> None:
    """Make create-only evidence directory entries durable after power loss."""
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def verify_product_build_context(source: Path) -> None:
    """Dockerfiles belong to the immutable Product checkout, not the Harness repo."""
    for relative in ("ops/coolify/Dockerfile", "ops/coolify/Dockerfile.ci"):
        try:
            info = (source / relative).lstat()
        except OSError as exc:
            raise Refused("product_dockerfile_missing") from exc
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size < 65536:
            raise Refused("product_dockerfile_untrusted")


def guest_ci(source: Path, sha: str) -> str:
    LOG_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    LOG_ROOT.chmod(0o700)
    if Path("/var/lib/zis-ci-guest/.docker/config.json").exists():
        raise Refused("persistent_guest_docker_credentials_present")
    log_dir = LOG_ROOT / require_sha(sha)
    log_dir.mkdir(mode=0o700, exist_ok=True)
    log_dir.chmod(0o700)
    if log_dir.stat().st_uid != 0 or LOG_ROOT.stat().st_uid != 0:
        raise Refused("log_directory_owner_untrusted")
    verify_product_build_context(source)
    fd, log_name = tempfile.mkstemp(prefix="attempt-", suffix=".pending", dir=log_dir)
    log = Path(log_name)
    shell = r'''
set -eu
test -n "$DOCKER_CONFIG" && test -d "$DOCKER_CONFIG"
test -z "$(find "$DOCKER_CONFIG" -mindepth 1 -maxdepth 1 -print -quit)"
test "$(dirname "$DOCKER_CONFIG")" = "$HOME"
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
docker run -d --name "$name" --network none --cap-drop ALL --pids-limit 256 --memory 512m --security-opt no-new-privileges -e SOURCE_COMMIT=EXPECTED_SHA product-ci:verified >/dev/null
docker exec "$name" cat /usr/share/nginx/html/__release.json | python3 -c 'import sys,json; x=json.load(sys.stdin); assert x["commit"]=="EXPECTED_SHA" and x["source"]=="zar-i-szlif/main"'
docker rm -f "$name" >/dev/null
if docker run --rm --network none --cap-drop ALL --pids-limit 256 --memory 512m --security-opt no-new-privileges product-ci:verified >"$negative" 2>&1; then
    echo NEGATIVE_VERSIONLESS_ALLOWED
    exit 89
fi
grep -q 'release provenance unavailable' "$negative"
echo ROOTLESS_EXACT_SOURCE_BUILD_AND_TEST_PASS
'''.replace("EXPECTED_TREE", command("git", "write-tree", cwd=source)).replace("EXPECTED_SHA", sha).replace("EXPECTED_SHORT", sha[:12])
    guest_home, env = isolated_guest_environment()
    argv = ["/usr/bin/prlimit", f"--fsize={MAX_LOG_BYTES}:{MAX_LOG_BYTES}", "--",
            "/usr/sbin/runuser", "-u", GUEST, "--", "env", *env, "/bin/sh", "-c", shell]
    passed = False
    try:
        with os.fdopen(fd, "wb") as output:
            try:
                p = subprocess.run(argv, cwd=source, stdout=output, stderr=subprocess.STDOUT,
                                   timeout=1800, env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"})
            except subprocess.TimeoutExpired as exc:
                raise Refused("rootless_ci_timeout") from exc
            output.flush()
            os.fsync(output.fileno())
        if p.returncode:
            raise Refused("rootless_ci_failed")
        if log.stat().st_size > MAX_LOG_BYTES:
            raise Refused("rootless_ci_log_limit_exceeded")
        log_bytes = log.read_bytes()  # bounded by RLIMIT_FSIZE on every child
        digest = hashlib.sha256(log_bytes).hexdigest()
        if b"ROOTLESS_EXACT_SOURCE_BUILD_AND_TEST_PASS" not in log_bytes:
            raise Refused("ci_milestone_unobserved")
        immutable = log_dir / (digest + ".log")
        try:
            os.link(log, immutable)  # create-only: no overwrite of referenced evidence
        except FileExistsError:
            if immutable.stat().st_uid != 0 or hashlib.sha256(immutable.read_bytes()).hexdigest() != digest:
                raise Refused("existing_log_digest_mismatch")
        os.chmod(immutable, 0o400)
        with immutable.open("rb") as evidence:
            os.fsync(evidence.fileno())
        fsync_directory(log_dir)
        passed = True
        return digest, immutable
    finally:
        shutil.rmtree(guest_home, ignore_errors=True)
        if passed:
            log.unlink(missing_ok=True)
            fsync_directory(log_dir)
        elif log.exists():
            # Preserve failed attempt but never let it impersonate signed evidence.
            log.rename(log.with_suffix(".failed"))

def receipt_key() -> bytes:
    KEY.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not KEY.exists():
        fd = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, os.urandom(32))
            os.fsync(fd)
        finally:
            os.close(fd)
        fsync_directory(KEY.parent)
    st = KEY.stat()
    if st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o600 or not stat.S_ISREG(st.st_mode):
        raise Refused("attestation_key_not_private")
    key = KEY.read_bytes()
    if len(key) != 32:
        raise Refused("attestation_key_invalid")
    return key

def _write_once(name: Path, data: bytes) -> None:
    """Do not mutate signed evidence, even during retry or crash recovery."""
    with tempfile.NamedTemporaryFile(mode="wb", prefix="receipt-", suffix=".pending",
                                     dir=name.parent, delete=False) as out:
        temporary = Path(out.name)
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    try:
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, name)  # O_EXCL equivalent; no replacement ever
        except FileExistsError as exc:
            raise Refused("attestation_already_exists") from exc
        fsync_directory(name.parent)
    finally:
        temporary.unlink(missing_ok=True)
        fsync_directory(name.parent)


def verified_existing(sha: str, expected_tree: str, key: bytes) -> dict | None:
    """Read-only reuse of complete trusted signed evidence; corrupt = refusal."""
    receipt = RECEIPTS / (require_sha(sha) + ".json")
    if not receipt.exists():
        return None
    try:
        info = os.stat(receipt, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > 4096):
            raise Refused("existing_attestation_untrusted")
        record = json.loads(receipt.read_bytes())
    except (OSError, ValueError) as exc:
        raise Refused("existing_attestation_unreadable") from exc
    if (not verify(record, key) or record.get("sha") != sha
            or record.get("tree") != expected_tree or record.get("exit_code") != 0
            or record.get("runner") != "zis-ci-guest-rootless"):
        raise Refused("existing_attestation_integrity_failed")
    candidate = record.get("log_path")
    digest = record.get("log_sha256")
    if (not isinstance(candidate, str) or not isinstance(digest, str)
            or not re.fullmatch(r"[a-f0-9]{64}", digest)):
        raise Refused("existing_attestation_log_missing")
    safe = LOG_ROOT / sha / (digest + ".log")
    if candidate != str(safe):
        raise Refused("existing_attestation_log_path_untrusted")
    try:
        meta = os.stat(safe, follow_symlinks=False)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or meta.st_nlink != 1
                or stat.S_IMODE(meta.st_mode) != 0o400):
            raise Refused("existing_attestation_log_untrusted")
        log_digest = hashlib.sha256(safe.read_bytes()).hexdigest()
    except OSError as exc:
        raise Refused("existing_attestation_log_unreadable") from exc
    if log_digest != digest:
        raise Refused("existing_attestation_log_tampered")
    return record


def store_receipt(payload: dict, key: bytes) -> Path:
    RECEIPTS.mkdir(mode=0o700, parents=True, exist_ok=True)
    name = RECEIPTS / (payload["sha"] + ".json")
    record = dict(payload, signature=sign(payload, key))
    _write_once(name, canonical(record) + b"\n")
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
    _write_once(name, canonical(record) + b"\n")
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
        key = receipt_key()
        prior = verified_existing(sha, tree, key)
        path = RECEIPTS / (sha + ".json")
        premerge = RECEIPTS / ("premerge-" + sha + ".json")
        if prior:
            if not premerge.is_file():
                raise Refused("signed_evidence_partial_premerge_missing")
            result = "already_attested"
        else:
            if premerge.exists():
                raise Refused("orphan_premerge_attestation_untrusted")
            source = prepare_source(sha, tree, tar, uid)
            log_sha, log_path = guest_ci(source, sha)
            payload = {"schema_version": 2, "sha": sha, "tree": tree,
                       "runner": "zis-ci-guest-rootless", "runner_uid": uid,
                       "command": "docker build && npm run validate:code (network none) && docker build",
                       "exit_code": 0, "log_sha256": log_sha, "log_path": str(log_path),
                       "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            path = store_receipt(payload, key)
            premerge = store_premerge_receipt(payload)
            result = "attested"
    print(json.dumps({"result": result, "sha": sha, "tree": tree,
                      "runner_uid": uid, "receipt": str(path),
                      "premerge_receipt": str(premerge)}, sort_keys=True))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Refused, OSError, ValueError, TimeoutError) as exc:
        print(json.dumps({"result": "denied", "reason": str(exc) if isinstance(exc, Refused) else "attester_io_failure"}))
        raise SystemExit(78)
