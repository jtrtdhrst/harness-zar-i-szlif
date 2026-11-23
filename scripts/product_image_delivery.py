#!/usr/bin/env python3
"""Build, push and deploy the product image for the current ci-approved SHA.

The source promotion controller advances ci-approved only after the Multica
gate. This worker closes the remaining manual delivery gap: image build, local
registry push, Coolify image tag + SOURCE_COMMIT, deploy and public readback.
"""
import argparse
import fcntl
import json
import os
import re
import stat
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = "jtrtdhrst/zar-i-szlif"
APP_UUID = "cs847jiwtuq5rlm8ntjeohgf"
REGISTRY = "127.0.0.1:5000"
IMAGE = "zar-i-szlif-web"
STATE_DIR = Path("/var/lib/multica-image-delivery")
SOURCE_DIR = STATE_DIR / "src"
COOLIFY = "http://127.0.0.1:8001/api/v1"
COOLIFY_TOKEN = Path("/root/coolify-secrets/coolify_api_token")
GITHUB_TOKEN = Path("/etc/multica-git-credential/roles/implementer.json")
MARKER = Path("/var/lib/paperclip-gitops/zis-image-promotion-ready.json")
PUBLIC_RELEASE = "https://panel.zariszlif.pl/__release.json"
PUBLIC_HEALTH = "https://panel.zariszlif.pl/healthz"
LOCK = STATE_DIR / "delivery.lock"
STATE = STATE_DIR / "state.json"

COMMIT_SHA_RE = re.compile(r"[a-f0-9]{40}")


def valid_commit_sha(value):
    return isinstance(value, str) and COMMIT_SHA_RE.fullmatch(value) is not None


def ensure_owned_directory(path, private=True):
    """Never trust pre-existing state directories or directory symlinks."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700 if private else 0o755)
    info = path.lstat()
    mode = stat.S_IMODE(info.st_mode)
    if (not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_gid != os.getegid()
            or mode & 0o022
            or (private and mode & 0o077)):
        raise PermissionError("untrusted_state_directory")


def atomic_private_json(path, value):
    """Create a fresh O_EXCL/0600 temp inode; never follow a planted .tmp symlink."""
    dirfd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY |
                    os.O_NOFOLLOW | os.O_CLOEXEC)
    name = f".{path.name}.{os.urandom(16).hex()}.tmp"
    created = False
    try:
        info = os.fstat(dirfd)
        if (not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_gid != os.getegid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise PermissionError("untrusted_state_directory")
        descriptor = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                             os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dirfd)
        created = True
        with os.fdopen(descriptor, "w") as file:
            json.dump(value, file, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path.name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        created = False
        os.fsync(dirfd)
    finally:
        if created:
            os.unlink(name, dir_fd=dirfd)
        os.close(dirfd)


def open_owned_state_file(path, append=False):
    """Open one trusted root-owned regular inode without following symlinks."""
    dirfd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY |
                    os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        d = os.fstat(dirfd)
        if (not stat.S_ISDIR(d.st_mode) or d.st_uid != os.geteuid()
                or d.st_gid != os.getegid()
                or stat.S_IMODE(d.st_mode) & 0o077):
            raise PermissionError("untrusted_state_directory")
        flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
        if append:
            flags |= os.O_APPEND
        fd = os.open(path.name, flags, 0o600, dir_fd=dirfd)
        try:
            f = os.fstat(fd)
            if (not stat.S_ISREG(f.st_mode)
                    or f.st_uid != os.geteuid()
                    or f.st_gid != os.getegid()
                    or stat.S_IMODE(f.st_mode) & 0o077
                    or f.st_nlink != 1):
                raise PermissionError("untrusted_state_file")
            return fd
        except BaseException:
            os.close(fd)
            raise
    finally:
        os.close(dirfd)


def read_build_attestation(expected_uid=0, expected_gid=0):
    """Read the marker from one validated inode under a non-writable directory.

    Directory and file are opened with O_NOFOLLOW. Metadata is checked using
    fstat of the SAME descriptors from which the JSON bytes are consumed.
    """
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    dirfd = os.open(str(MARKER.parent), flags)
    try:
        parent = os.fstat(dirfd)
        if (not stat.S_ISDIR(parent.st_mode)
                or parent.st_uid != expected_uid
                or parent.st_gid != expected_gid
                or stat.S_IMODE(parent.st_mode) & 0o077):
            raise PermissionError("untrusted_marker_directory")
        fd = os.open(MARKER.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                     dir_fd=dirfd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode)
                    or info.st_uid != expected_uid or info.st_gid != expected_gid
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1 or info.st_size > 8192):
                raise PermissionError("untrusted_build_attestation")
            with os.fdopen(fd, "r", encoding="utf-8") as file:
                fd = -1
                raw = file.read(8193)
            if len(raw) > 8192:
                raise ValueError("oversized_build_attestation")
            return json.loads(raw)
        finally:
            if fd >= 0:
                os.close(fd)
    finally:
        os.close(dirfd)


def github_token():
    return json.loads(GITHUB_TOKEN.read_text())["token"]


def github_json(path):
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Authorization": "token " + github_token(), "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "multica-image-delivery"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def ref_sha(ref):
    return github_json(f"/repos/{REPO}/git/ref/heads/{ref}")["object"]["sha"]


def live_sha():
    request = urllib.request.Request(PUBLIC_RELEASE, headers={"Cache-Control": "no-cache", "User-Agent": "multica-image-delivery"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)["commit"]


def target_readback(sha, *, image=None, digest=None):
    """Read-only proof that the exact approved image is actually serving PUBLIC traffic.

    Fail closed. A release JSON value alone, a healthy container or a mutable
    tag is insufficient. No credentials, full Docker labels or user messages
    are returned or logged.
    """
    import hashlib,re,stat
    def deny(reason):
        return {"ok":False,"reason":reason}
    if not isinstance(sha,str) or not re.fullmatch(r"[a-f0-9]{40}",sha):
        return deny("invalid_sha")
    try:
        if (image is None) != (digest is None):
            return deny("incomplete_candidate_proof")
        try:
            if image is None:
                proof = read_build_attestation()
            else:
                # Internal candidate readback: independently verify the live
                # runtime before creating a persistent verified receipt.
                proof = {"schema_version":1, "verified":True,
                         "registry":REGISTRY, "runner":"zis-local-build",
                         "coolify_image_app_uuid":APP_UUID,
                         "sha":sha, "image":image, "digest":digest}
        except (OSError, ValueError, PermissionError):
            return deny("untrusted_build_attestation")
        image=f"{REGISTRY}/{IMAGE}:{sha}"
        digest=proof.get("digest")
        if (proof.get("schema_version")!=1 or proof.get("verified") is not True
                or proof.get("runner")!="zis-local-build"
                or proof.get("coolify_image_app_uuid")!=APP_UUID
                or proof.get("registry")!=REGISTRY
                or proof.get("sha")!=sha or proof.get("image")!=image
                or not isinstance(digest,str) or not re.fullmatch(r"sha256:[a-f0-9]{64}",digest)):
            return deny("build_attestation_mismatch")
        containers=subprocess.run(["docker","ps","--format","{{.Names}}"],
                                  capture_output=True,text=True,timeout=12,check=True).stdout.splitlines()
        matches=[n for n in containers if n==APP_UUID or n.startswith(APP_UUID+"-")]
        if len(matches)!=1:
            return deny("target_container_not_unique")
        name=matches[0]
        raw=subprocess.run(["docker","inspect","--format",
                "{{.Image}}|{{.Config.Image}}|{{.State.Status}}",name],
                capture_output=True,text=True,timeout=12,check=True).stdout.strip().split("|")
        if len(raw) != 3 or raw[1:] != [image, "running"]:
            return deny("target_runtime_digest_or_ref_mismatch")
        image_metadata = subprocess.run(
            ["docker", "image", "inspect", "--format",
             "{{.Id}}|{{json .RepoDigests}}", image],
            capture_output=True, text=True, timeout=12, check=True
        ).stdout.strip().split("|", 1)
        if len(image_metadata) != 2:
            return deny("target_runtime_digest_or_ref_mismatch")
        image_id = image_metadata[0]
        repo_digests = json.loads(image_metadata[1])
        expected_repo_digest = f"{REGISTRY}/{IMAGE}@{digest}"
        if (not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id)
                or raw[0] != image_id
                or not isinstance(repo_digests, list)
                or expected_repo_digest not in repo_digests):
            return deny("target_runtime_digest_or_ref_mismatch")
        release=subprocess.run(["docker","exec",name,"cat",
                "/usr/share/nginx/html/__release.json"],
                capture_output=True,text=True,timeout=12,check=True)
        payload=json.loads(release.stdout)
        if payload.get("commit")!=sha or payload.get("source")!="zar-i-szlif/main":
            return deny("container_release_mismatch")
        checksum=subprocess.run(["docker","exec",name,"sha256sum",
                "/usr/share/nginx/html/index.html"],capture_output=True,
                text=True,timeout=12,check=True).stdout.split()[0]
        if not re.fullmatch(r"[a-f0-9]{64}",checksum):
            return deny("invalid_container_html_hash")
        with urllib.request.urlopen(urllib.request.Request(
                "https://panel.zariszlif.pl/",
                headers={"Cache-Control":"no-cache","User-Agent":"multica-image-delivery-readback"}),
                timeout=12) as response:
            if response.status!=200: return deny("public_html_not_200")
            html=response.read(2*1024*1024+1)
        if len(html)>2*1024*1024 or hashlib.sha256(html).hexdigest()!=checksum:
            return deny("public_html_not_target_container")
        if live_sha()!=sha:
            return deny("public_release_sha_mismatch")
        with urllib.request.urlopen(PUBLIC_HEALTH,timeout=12) as response:
            if response.status!=200: return deny("public_health_unavailable")
        return {"ok":True,"reason":"exact_image_digest_and_public_content_verified",
                "sha":sha,"image_digest":digest}
    except (OSError,ValueError,KeyError,IndexError,subprocess.CalledProcessError,
            subprocess.TimeoutExpired,urllib.error.URLError):
        return deny("target_readback_unavailable")

def coolify(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        COOLIFY + path, data=data, method=method,
        headers={"Authorization": "Bearer " + COOLIFY_TOKEN.read_text().strip(),
                 "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        return response.status, json.loads(raw) if raw else {}


def download_source(sha):
    # A user-provided --sha must never become a path component without
    # validation. Refuse path traversal before any download or filesystem write.
    if not valid_commit_sha(sha):
        raise ValueError("invalid_source_sha")
    ensure_owned_directory(STATE_DIR)
    ensure_owned_directory(SOURCE_DIR, private=False)
    tarfd, tarname = tempfile.mkstemp(prefix=f"src-{sha}-",
                                       suffix=".tar.gz", dir=str(SOURCE_DIR))
    tarball = Path(tarname)
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/tarball/{sha}",
        headers={"Authorization": "token " + github_token(), "Accept": "application/vnd.github+json",
                 "User-Agent": "multica-image-delivery"},
    )
    try:
        with os.fdopen(tarfd, "wb") as out:
            with urllib.request.urlopen(request, timeout=120) as response:
                shutil.copyfileobj(response, out)
        work = SOURCE_DIR / sha
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        with tarfile.open(tarball) as archive:
            archive.extractall(work, filter="data")
        roots = [item for item in work.iterdir() if item.is_dir()]
        if len(roots) != 1:
            raise RuntimeError("unexpected source archive layout")
        return roots[0]
    finally:
        tarball.unlink(missing_ok=True)


def build_and_push(sha, log):
    context = download_source(sha)
    image = f"{REGISTRY}/{IMAGE}:{sha}"
    with os.fdopen(open_owned_state_file(log, append=True), "ab") as output:
        result = subprocess.run(
            ["docker", "build", "--file", "ops/coolify/Dockerfile", "--tag", image, "."],
            cwd=context, stdout=output, stderr=subprocess.STDOUT, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("docker build failed")
        result = subprocess.run(["docker", "push", image], stdout=output, stderr=subprocess.STDOUT, check=False)
        if result.returncode != 0:
            raise RuntimeError("docker push failed")
    digest = subprocess.run(
        ["docker", "inspect", "--format", "{{index .RepoDigests 0}}", image],
        capture_output=True, text=True, check=True,
    ).stdout.strip().split("@", 1)[-1]
    shutil.rmtree(context.parent, ignore_errors=True)
    return image, digest


def update_marker(sha, image, digest):
    payload = {
        "schema_version": 1, "verified": True, "registry": REGISTRY,
        "coolify_image_app_uuid": APP_UUID, "runner": "zis-local-build",
        "image": image, "digest": digest, "sha": sha,
        "verified_at": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()),
    }
    atomic_private_json(MARKER, payload)


def deploy(sha):
    coolify("PATCH", f"/applications/{APP_UUID}", {"docker_registry_image_tag": sha})
    coolify("PATCH", f"/applications/{APP_UUID}/envs",
            {"key": "SOURCE_COMMIT", "value": sha, "is_runtime": True, "is_buildtime": False})
    status, body = coolify("POST", "/deploy", {"uuid": APP_UUID})
    return status, body


def wait_live(sha, attempts=90, interval=10, *, image=None, digest=None):
    for _ in range(attempts):
        try:
            if target_readback(sha, image=image, digest=digest)["ok"]:
                return True
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(interval)
    return False


def restore_previous(previous_sha):
    """Restore the last running release and independently verify its content."""
    if not valid_commit_sha(previous_sha):
        return {"healthy": False, "reason": "invalid_previous_sha"}
    status, body = deploy(previous_sha)
    deployment = (body.get("deployments", [{}])[0].get("deployment_uuid")
                  if isinstance(body, dict) else None)
    healthy = wait_live(previous_sha, attempts=12, interval=5)
    return {"sha": previous_sha, "healthy": healthy,
            "deploy_http": status, "deployment": deployment}


def save(state):
    atomic_private_json(STATE, state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    try:
        ensure_owned_directory(STATE_DIR)
        ensure_owned_directory(STATE_DIR / "docker")
    except (OSError, ValueError):
        print(json.dumps({"result": "untrusted_state_directory"}), file=sys.stderr)
        return 1
    try:
        lockfd = open_owned_state_file(LOCK)
    except (OSError, ValueError):
        print(json.dumps({"result": "untrusted_state_file"}), file=sys.stderr)
        return 1
    with os.fdopen(lockfd, "a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"result": "busy"}))
            return 0
        approved = ref_sha("ci-approved")
        if not valid_commit_sha(approved):
            print(json.dumps({"result": "invalid_ci_approved_sha"}), file=sys.stderr)
            return 1
        if args.sha is not None:
            if not valid_commit_sha(args.sha):
                print(json.dumps({"result": "invalid_source_sha"}), file=sys.stderr)
                return 1
            if args.sha != approved:
                print(json.dumps({"result": "sha_not_ci_approved"}), file=sys.stderr)
                return 1
        target = approved
        current = live_sha()
        if target == current and not args.force:
            proof=target_readback(target)
            if not proof["ok"]:
                print(json.dumps({"result":"readback_unverified","sha":target,
                                  "reason":proof["reason"]}),file=sys.stderr)
                return 1
            print(json.dumps({"result":"already_live_verified","sha":target,
                              "image_digest":proof["image_digest"]}))
            return 0
        if args.plan:
            print(json.dumps({"result": "would_deliver", "sha": target, "live": current}))
            return 0
        log = STATE_DIR / f"build-{target}.log"
        deployment_started = False
        try:
            image, digest = build_and_push(target, log)
            deployment_started = True
            status, body = deploy(target)
            deployment = body.get("deployments", [{}])[0].get("deployment_uuid") if isinstance(body, dict) else None
            healthy = wait_live(target, image=image, digest=digest)
            if not healthy:
                # The new image was not verified. Restore the prior approved
                # release; never set a fresh verified marker on this path.
                rollback = restore_previous(current)
                save({"sha": target, "previous": current, "image": image,
                      "digest": digest, "deployment": deployment, "healthy": False,
                      "rollback": rollback,
                      "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                print(json.dumps({"result": "readback_failed_rollback",
                                  "sha": target, "digest": digest,
                                  "rollback": rollback}), file=sys.stderr)
                return 1
            # Certification comes strictly AFTER positive runtime and public
            # content readback, never after build or deployment request alone.
            update_marker(target, image, digest)
            save({"sha": target, "previous": current, "image": image, "digest": digest,
                  "deployment": deployment, "healthy": True,
                  "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            print(json.dumps({"result": "deployed", "sha": target, "digest": digest,
                              "deployment": deployment, "healthy": True,
                              "deploy_http": status}))
            return 0
        except Exception as error:
            rollback = None
            if deployment_started:
                try:
                    rollback = restore_previous(current)
                except Exception as rollback_error:
                    rollback = {"healthy": False, "reason": "rollback_execution_failed",
                                "error": str(rollback_error)[:100]}
            save({"sha": target, "previous": current, "healthy": False,
                  "rollback": rollback, "error": str(error)[:200],
                  "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            print(json.dumps({"result": "error", "sha": target,
                              "rollback": rollback, "error": str(error)[:200]}), file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
