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
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = "miloszspyrka-code/zar-i-szlif"
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


def trusted_directory(path, *, private=False):
    """Refuse symlinked, foreign-owned or writable-by-others release state."""
    info = path.lstat()
    mode = stat.S_IMODE(info.st_mode)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or (private and mode != 0o700)
            or (not private and bool(mode & 0o022))):
        raise RuntimeError("untrusted_release_directory")


def trusted_directory_fd(path, *, private=True):
    """Hold a non-symlink directory descriptor and verify this exact inode."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path, flags)
    info = os.fstat(fd)
    mode = stat.S_IMODE(info.st_mode)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or (private and mode != 0o700)
            or (not private and bool(mode & 0o022))):
        os.close(fd)
        raise RuntimeError("untrusted_release_directory")
    return fd


def read_marker_protected(path):
    """Same opened inode is checked and decoded; never follow a marker symlink."""
    dfd = trusted_directory_fd(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
        with os.fdopen(fd, "r", encoding="utf-8") as reader:
            info = os.fstat(reader.fileno())
            if (info.st_uid != os.geteuid() or not stat.S_ISREG(info.st_mode)
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise RuntimeError("untrusted_build_attestation")
            return json.load(reader)
    finally:
        os.close(dfd)


def atomic_json_replace(path, payload):
    """Write exclusively under a verified dirfd, never through stale symlinks."""
    dfd = trusted_directory_fd(path.parent)
    temp_name = path.with_suffix(".tmp").name
    created = False
    try:
        fd = os.open(temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                     os.O_NOFOLLOW, 0o600, dir_fd=dfd)
        created = True
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path.name, src_dir_fd=dfd, dst_dir_fd=dfd)
        created = False
    finally:
        if created:
            os.unlink(temp_name, dir_fd=dfd)
        os.close(dfd)


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


def target_readback(sha):
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
        try:
            proof = read_marker_protected(MARKER)
        except (OSError, RuntimeError, ValueError):
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
        if len(raw)!=3 or raw[1:] != [image, "running"]:
            return deny("target_runtime_digest_or_ref_mismatch")
        # Docker's config image ID and registry manifest digest are distinct
        # identifiers; compare each to its authoritative source separately.
        meta=subprocess.run(["docker","image","inspect","--format",
                "{{.Id}}|{{json .RepoDigests}}",image],
                capture_output=True,text=True,timeout=12,check=True).stdout.strip().split("|",1)
        if len(meta)!=2 or meta[0]!=raw[0] or not re.fullmatch(r"sha256:[a-f0-9]{64}",meta[0]):
            return deny("target_runtime_image_id_mismatch")
        repositories=json.loads(meta[1])
        if (not isinstance(repositories,list)
                or f"{REGISTRY}/{IMAGE}@{digest}" not in repositories):
            return deny("repository_digest_mismatch")
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
    trusted_directory(STATE_DIR, private=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    trusted_directory(SOURCE_DIR)
    tarball = SOURCE_DIR / f"src-{sha}.tar.gz"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/tarball/{sha}",
        headers={"Authorization": "token " + github_token(), "Accept": "application/vnd.github+json",
                 "User-Agent": "multica-image-delivery"},
    )
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW
    with urllib.request.urlopen(request, timeout=120) as response, \
         os.fdopen(os.open(tarball, flags, 0o600), "wb") as out:
        shutil.copyfileobj(response, out)
    work = SOURCE_DIR / sha
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    with tarfile.open(tarball) as archive:
        archive.extractall(work, filter="data")
    roots = [item for item in work.iterdir() if item.is_dir()]
    if len(roots) != 1:
        raise RuntimeError("unexpected source archive layout")
    tarball.unlink()
    return roots[0]


def build_and_push(sha, log):
    context = download_source(sha)
    image = f"{REGISTRY}/{IMAGE}:{sha}"
    fd = os.open(log, os.O_CREAT | os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "ab") as output:
        info = os.fstat(output.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise RuntimeError("untrusted_build_log")
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
    trusted_directory(MARKER.parent, private=True)
    atomic_json_replace(MARKER, json.dumps(payload) + "\n")


def deploy(sha):
    coolify("PATCH", f"/applications/{APP_UUID}", {"docker_registry_image_tag": sha})
    coolify("PATCH", f"/applications/{APP_UUID}/envs",
            {"key": "SOURCE_COMMIT", "value": sha, "is_runtime": True, "is_buildtime": False})
    status, body = coolify("POST", "/deploy", {"uuid": APP_UUID})
    return status, body


def wait_live(sha, attempts=90, interval=10):
    for _ in range(attempts):
        try:
            if target_readback(sha)["ok"]:
                return True
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(interval)
    return False


def save(state):
    trusted_directory(STATE_DIR, private=True)
    atomic_json_replace(STATE, json.dumps(state, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    trusted_directory(STATE_DIR, private=True)
    docker_dir = STATE_DIR / "docker"
    docker_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    trusted_directory(docker_dir, private=True)
    with open(LOCK, "a+") as lock:
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
        try:
            image, digest = build_and_push(target, log)
            update_marker(target, image, digest)
            status, body = deploy(target)
            deployment = body.get("deployments", [{}])[0].get("deployment_uuid") if isinstance(body, dict) else None
            healthy = wait_live(target)
            save({"sha": target, "previous": current, "image": image, "digest": digest,
                  "deployment": deployment, "healthy": healthy,
                  "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            print(json.dumps({"result": "deployed" if healthy else "readback_failed",
                              "sha": target, "digest": digest, "deployment": deployment,
                              "healthy": healthy, "deploy_http": status}))
            return 0 if healthy else 1
        except Exception as error:
            save({"sha": target, "previous": current, "healthy": False, "error": str(error)[:200],
                  "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            print(json.dumps({"result": "error", "sha": target, "error": str(error)[:200]}), file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
