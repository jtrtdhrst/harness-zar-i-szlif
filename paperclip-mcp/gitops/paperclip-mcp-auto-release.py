#!/usr/bin/env python3
"""Fail-closed GitOps for the existing Coolify-managed Paperclip MCP service.

Only merged main PRs to the allowlisted harness repository can release.
Images are built and tested from the exact Git SHA, and service health gates
automatic rollback. Existing Coolify Compose volumes, entrypoint and secrets
are unchanged; no GitHub credential is copied or printed.
"""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

REPO = "miloszspyrka-code/harness-zar-i-szlif"
REPO_URL = "https://github.com/" + REPO + ".git"
CORE = "paperclip-2omzqpy8dxgmhuwfbzo7bvvv"
COOLIFY = "coolify"
COOLIFY_APP_ID = 1
COOLIFY_GITHUB_APP_ID = 5398752
COOLIFY_INSTALLATION_ID = 173456397
PROJECT_ID = "gevr1m6rdj4t4fbhcjvqv8gg"
SERVICE = "paperclip-mcp"
COMPOSE = "/data/coolify/services/" + PROJECT_ID + "/docker-compose.yml"
IMAGE = "paperclip-mcp:gitops-active"
BASE = "ghcr.io/paperclipai/paperclip:2026.1023.0"
STATE_DIR = Path("/var/lib/paperclip-gitops")
STATE = STATE_DIR / "paperclip-mcp.json"
PUBLIC = "https://paperclip-mcp.zariszlif.pl"
HEX = re.compile(r"^[0-9a-f]{40}$")
WATCHED_PREFIXES = (
    "paperclip-mcp/mcp-gateway/",
    "paperclip-mcp/src/",
    "paperclip-mcp/plugin-runtime/",
    "paperclip-mcp/plugin-skills/",
)
WATCHED_FILES = ("paperclip-mcp/Dockerfile", "paperclip-mcp/entrypoint.sh")
TEST_FILES = (
    "src/github-app-rotation.test.ts",
    "src/git-publication-role.test.ts",
    "src/git-credential-projection.test.ts",
    "src/p1-git.test.ts",
    "src/live-verify.test.ts",
    "src/workspace-native.test.ts",
)

def is_component_change(name):
    return name in WATCHED_FILES or any(name.startswith(prefix) for prefix in WATCHED_PREFIXES)

def validate_sha(sha):
    return isinstance(sha, str) and bool(HEX.fullmatch(sha))

def run(argv, timeout=100, stdin=None, allow_fail=False):
    r = subprocess.run(argv, input=stdin, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=timeout, text=stdin is None)
    if r.returncode and not allow_fail:
        # Intentionally omit command output: Docker build/transport logs may
        # contain untrusted content. No authentication material in journald.
        raise RuntimeError("Command failed: " + str(argv[0:2]) + " (exit " + str(r.returncode) + ")")
    return r

def docker_core(*argv, timeout=100):
    return run(["docker", "exec", CORE, *argv], timeout=timeout).stdout.strip()

def remote_main():
    rows = docker_core("git", "ls-remote", REPO_URL, "refs/heads/main")
    parts = rows.split()
    if len(parts) != 2 or not validate_sha(parts[0]) or parts[1] != "refs/heads/main":
        raise RuntimeError("Remote main reference unavailable/invalid")
    return parts[0]

def read_state():
    if not STATE.exists():
        return {}
    if STATE.is_symlink() or STATE.stat().st_size > 20000:
        raise RuntimeError("GitOps state file is unsafe")
    o = json.loads(STATE.read_text())
    for field in ("last_checked_sha", "deployed_sha"):
        if o.get(field) and not validate_sha(o[field]):
            raise RuntimeError("GitOps state SHA invalid")
    return o

def save_state(data):
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = STATE.with_suffix(".tmp")
    fd = os.open(str(temp), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, sort_keys=True, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, STATE)

def assess_release_attestation(data):
    """Deployment proof is an actual merged main PR and its successful CI.

    GitHub installation identity is shared. An invented second GitHub reviewer
    is not a substitute for CHO/CTO's first-class Paperclip review. The native
    issue review lifecycle owns that decision; GitOps verifies the delivery
    artifact and CI, and is never permitted to fabricate approval.
    """
    if not isinstance(data, dict) or data.get("verified") is not True:
        raise RuntimeError("Commit is not associated with a merged main PR")
    pr = data.get("pr")
    head = data.get("head_sha")
    if not isinstance(pr, int) or pr <= 0 or not validate_sha(head):
        raise RuntimeError("Merged PR identity / head SHA invalid")
    if data.get("checks_http") != 200:
        raise RuntimeError("GitHub Actions check-runs unreadable")
    checks = data.get("checks")
    total = data.get("checks_total")
    if not isinstance(checks, list) or not isinstance(total, int):
        raise RuntimeError("GitHub Actions check-runs malformed")
    if total > 100 or total != len(checks):
        raise RuntimeError("GitHub Actions checks pagination / count unverified")
    matching = [c for c in checks if isinstance(c, dict) and c.get("name") == "validate-paperclip-mcp"]
    if len(matching) != 1 or matching[0].get("status") != "completed" or matching[0].get("conclusion") != "success":
        raise RuntimeError("Paperclip MCP CI must complete successfully on the PR head")
    if any(not isinstance(c, dict) or c.get("conclusion") not in ("success", "skipped", "neutral")
           or c.get("status") != "completed" for c in checks):
        raise RuntimeError("A GitHub Actions check is pending, failing or unreadable")
    return pr

def assess_native_review_evidence(evidence, issue_id, pr_number, head_sha):
    """Deny until a trusted Paperclip response verifier and read auth exist."""
    raise RuntimeError("Authoritative Paperclip review decision unavailable")

def native_review_evidence(issue_id, pr_number, head_sha):
    """No live Paperclip read adapter is configured; fail closed until one exists."""
    return None

def verified_pr(sha):
    # The existing Coolify GitHub App reads PR provenance and green CI.
    # CHO/CTO's independent review belongs to Paperclip's native decision
    # record, not an extra artificial GitHub account/review requirement.
    if not validate_sha(sha):
        raise RuntimeError("Invalid merge SHA")
    php = (
        '$a=App\\Models\\GithubApp::findOrFail(1);'
        'if((int)$a->app_id!==5398752||(int)$a->installation_id!==173456397){throw new \\RuntimeException("Wrong app");}'
        '$tok=generateGithubInstallationToken($a);'
        '$h=Illuminate\\Support\\Facades\\Http::GitHub($a->api_url,$tok);'
        '$sha="' + sha + '";'
        '$r=$h->get("/repos/miloszspyrka-code/harness-zar-i-szlif/commits/".$sha."/pulls");'
        'if(!$r->ok()){throw new \\RuntimeException("PR query refused");}'
        '$m=collect($r->json()??[])->first(fn($p)=>data_get($p,"base.ref")==="main"'
        '&&!blank(data_get($p,"merged_at"))&&data_get($p,"merge_commit_sha")===$sha);'
        'if(!$m){echo json_encode(["verified"=>false]);}'
        'else{'
        '$pr=data_get($m,"number");$head=data_get($m,"head.sha");'
        '$checks=$h->get("/repos/miloszspyrka-code/harness-zar-i-szlif/commits/".$head."/check-runs",["per_page"=>100]);'
        '$cs=collect($checks->json("check_runs")??[])->map(fn($v)=>["name"=>data_get($v,"name"),"status"=>data_get($v,"status"),"conclusion"=>data_get($v,"conclusion")])->all();'
        'echo json_encode(["verified"=>true,"pr"=>$pr,"head_sha"=>$head,'
        '"checks_http"=>$checks->status(),"checks"=>$cs,"checks_total"=>$checks->json("total_count")]);}'
    )
    r = run(["docker", "exec", COOLIFY, "php", "artisan", "tinker", "--execute=" + php], timeout=70)
    try:
        out = json.loads(r.stdout.strip())
    except (ValueError, json.JSONDecodeError) as err:
        raise RuntimeError("Coolify PR attestation response invalid") from err
    pr = assess_release_attestation(out)
    return {"number": pr, "head_sha": out["head_sha"]}

def get_container_id():
    r = run(["docker", "ps", "-q", "--filter", "label=com.docker.compose.project=" + PROJECT_ID,
             "--filter", "label=com.docker.compose.service=" + SERVICE])
    ids = [s for s in r.stdout.splitlines() if s.strip()]
    if len(ids) != 1:
        raise RuntimeError("Expected one current Coolify MCP container")
    return ids[0]

def container_info():
    cid = get_container_id()
    data = json.loads(run(["docker", "inspect", cid]).stdout)[0]
    health = (data["State"].get("Health") or {}).get("Status")
    return {"container": cid, "image_id": data["Image"], "image": data["Config"]["Image"],
            "running": data["State"]["Running"], "health": health,
            "revision": (data["Config"].get("Labels") or {}).get("org.opencontainers.image.revision")}

def assert_compose_armed():
    from pathlib import Path
    text = Path(COMPOSE).read_text()
    if "image: paperclip-mcp:gitops-active" not in text and "image: 'paperclip-mcp:gitops-active'" not in text:
        raise RuntimeError("Coolify Compose is not armed with the gitops-active image")
    if "paperclip-github-core-credentials" in text:
        raise RuntimeError("Legacy PAT mount unexpectedly restored")
    if "/paperclip/github-auth-bin/bootstrap" not in text or "PAPERCLIP_GITHUB_APP_TOKEN_FILE" not in text:
        raise RuntimeError("GitHub App bootstrap drifted")
    run(["docker", "compose", "-p", PROJECT_ID, "-f", COMPOSE, "config", "-q"])

def verify_anonymous_mcp_denial():
    # Cloudflare allows normal HTTP clients such as curl, but may respond 403
    # to Python-urllib's distinct TLS/UA fingerprint before MCP sees the
    # request. A literal external curl probe checks the actual public MCP
    # OAuth boundary, rather than mistaking Cloudflare bot policy for
    # gateway authentication failure. Never sends bearer credentials.
    body = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
    code = run([
        "curl", "--silent", "--show-error", "--max-time", "12",
        "--output", "/dev/null", "--write-out", "%{http_code}",
        "--request", "POST", PUBLIC + "/mcp",
        "--header", "Content-Type: application/json",
        "--header", "Accept: application/json, text/event-stream",
        "--data-binary", body,
    ], timeout=20).stdout.strip()
    if code != "401":
        raise RuntimeError("Anonymous public MCP must return 401; got " + str(code))

def public_health():
    req = urllib.request.Request(PUBLIC + "/health", headers={"User-Agent": "Paperclip-GitOps/1"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            if r.status != 200:
                raise RuntimeError("Public health non-200")
    except (urllib.error.URLError, TimeoutError) as err:
        raise RuntimeError("Public MCP health unavailable") from err
    # Every anonymous MCP request must still be denied at the OAuth boundary.
    verify_anonymous_mcp_denial()

def wait_healthy(expected_image_id, sha=None, seconds=115):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        try:
            c = container_info()
            if c["image_id"] == expected_image_id and c["running"] and c["health"] == "healthy":
                if sha and c["revision"] != sha:
                    raise RuntimeError("Runtime OCI revision label != source SHA")
                public_health()
                return c
        except RuntimeError:
            pass
        time.sleep(4)
    raise RuntimeError("Coolify MCP failed readiness / public OAuth check")

def compose_up():
    run(["docker", "compose", "-p", PROJECT_ID, "-f", COMPOSE,
         "up", "-d", "--no-deps", "--force-recreate", SERVICE], timeout=130)

def ensure_candidate_tests(tag):
    # Full targeted native Git and MCP smoke regression tests from the same
    # source image that will run in production. Deliberately no network auth.
    parts = " ".join(TEST_FILES)
    script = (
        "set -eu; mkdir -p /tmp/gitops-test; "
        "cp -r /opt/paperclip-mcp/src /tmp/gitops-test/src; "
        "ln -s /app/packages/mcp-server/node_modules /tmp/gitops-test/node_modules; "
        "cd /tmp/gitops-test; "
        "/app/node_modules/.bin/vitest run --root /tmp/gitops-test " + parts +
        " --maxWorkers=2 --reporter=dot"
    )
    run(["docker", "run", "--rm", "--entrypoint", "/bin/sh", tag, "-c", script], timeout=150)

def git_clone_and_changes(remote, previous):
    """Clone pinned main in the Core container; original credentials remain there."""
    path = docker_core("mktemp", "-d", "/tmp/harness-autorelease-XXXXXXXX")
    if not path.startswith("/tmp/harness-autorelease-"):
        raise RuntimeError("Unexpected staging directory")
    try:
        docker_core("git", "clone", "-q", "--single-branch", "-b", "main", REPO_URL, path + "/repo", timeout=110)
        checkout = docker_core("git", "-C", path + "/repo", "rev-parse", "HEAD")
        if checkout != remote:
            raise RuntimeError("Remote main changed during staging")
        if previous:
            o = run(["docker", "exec", CORE, "git", "-C", path + "/repo",
                     "merge-base", "--is-ancestor", previous, remote], allow_fail=True)
            if o.returncode:
                raise RuntimeError("main no longer extends the last checked commit (force push?)")
            files = docker_core("git", "-C", path + "/repo", "diff", "--name-only", previous, remote)
            changed = [f for f in files.splitlines() if f]
        else:
            changed = ["paperclip-mcp/src/INITIAL_BOOTSTRAP.ts"]
        return path, changed
    except Exception:
        run(["docker", "exec", CORE, "rm", "-rf", path], allow_fail=True)
        raise

def create_archive(path, tmp):
    archive = path + "/paperclip-mcp-source.tar.gz"
    docker_core("tar", "-czf", archive, "--exclude=node_modules", "--exclude=.git",
                "-C", path + "/repo/paperclip-mcp", ".", timeout=85)
    dest = str(Path(tmp) / "source.tar.gz")
    run(["docker", "cp", CORE + ":" + archive, dest], timeout=100)
    if Path(dest).stat().st_size < 10000:
        raise RuntimeError("Source artifact too small")
    return dest

def build_image(sha, tar_path):
    tag = "paperclip-mcp:gitops-" + sha
    with open(tar_path, "rb") as f:
        run(["docker", "build", "--build-arg", "PAPERCLIP_BASE=" + BASE,
             "--label", "org.opencontainers.image.revision=" + sha,
             "-t", tag, "-"], stdin=f.read(), timeout=300)
    ensure_candidate_tests(tag)
    image_id = run(["docker", "image", "inspect", tag, "--format", "{{.Id}}"]).stdout.strip()
    if not image_id.startswith("sha256:"):
        raise RuntimeError("Candidate lacks immutable Docker image ID")
    return tag, image_id

def process(plan=False):
    assert_compose_armed()
    state = read_state()
    remote = remote_main()
    previous = state.get("last_checked_sha")
    if remote == previous:
        print(json.dumps({"result":"already_checked","sha":remote,"deployed_sha":state.get("deployed_sha")}))
        return 0
    path, changed = git_clone_and_changes(remote, previous)
    try:
        watched = [f for f in changed if is_component_change(f)]
        if not watched:
            if not plan:
                state["last_checked_sha"] = remote
                state["last_checked_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                save_state(state)
            print(json.dumps({"result":"not_a_paperclip_mcp_change","sha":remote,"changed_paths_count":len(changed)}))
            return 0
        pr = verified_pr(remote)
        assess_native_review_evidence(native_review_evidence(os.environ.get("PAPERCLIP_RELEASE_ISSUE_ID"), pr["number"], pr["head_sha"]),
                                      os.environ.get("PAPERCLIP_RELEASE_ISSUE_ID"), pr["number"], pr["head_sha"])
        if plan:
            print(json.dumps({"result":"ready","sha":remote,"merged_pr":pr["number"],"affected_paths_count":len(watched)}))
            return 0
        failure = state.get("failed_release") or {}
        if failure.get("sha") == remote and time.time() - failure.get("time",0) < 600:
            print(json.dumps({"result":"failure_backoff","sha":remote,"retry_after_seconds":600}))
            return 0
        with tempfile.TemporaryDirectory(prefix="paperclip-mcp-gitops-") as tmp:
            archive = create_archive(path, tmp)
            tag, image_id = build_image(remote, archive)
        if remote_main() != remote:
            raise RuntimeError("main changed while preparing candidate; refusing stale release")
        old = container_info()
        if old["health"] != "healthy":
            raise RuntimeError("Existing Coolify service not healthy; refusing automatic replacement")
        run(["docker", "tag", tag, IMAGE])
        try:
            compose_up()
            result = wait_healthy(image_id, sha=remote)
        except Exception:
            run(["docker", "tag", old["image_id"], IMAGE], allow_fail=True)
            try:
                compose_up()
                wait_healthy(old["image_id"], seconds=115)
                print(json.dumps({"result":"rolled_back","previous_image_id":old["image_id"]}))
            except Exception:
                print(json.dumps({"result":"rollback_incomplete","previous_image_id":old["image_id"]}))
            raise
        state.update({
            "last_checked_sha":remote,
            "last_checked_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "deployed_sha":remote,
            "deployed_image_id":image_id,
            "previous_image_id":old["image_id"],
            "merged_pr":pr["number"],
            "last_successful_release":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "failed_release":None,
        })
        save_state(state)
        print(json.dumps({"result":"deployed","source_sha":remote,
                          "merged_pr":pr["number"],"image_id":image_id,"healthy":result["health"]}))
        return 0
    finally:
        run(["docker", "exec", CORE, "rm", "-rf", path], allow_fail=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    opts = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError("GitOps controller requires root")
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = STATE_DIR / "paperclip-mcp.lock"
    with open(lock, "a+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            return process(opts.plan)
        except Exception as err:
            state = read_state()
            if not opts.plan:
                try:
                    failed_sha = remote_main()
                except Exception:
                    failed_sha = None
                state["failed_release"] = {"sha":failed_sha,
                                           "time":time.time(), "error_type":type(err).__name__}
                save_state(state)
            print(json.dumps({"result":"error","kind":type(err).__name__,"message":str(err)[:240]}), file=sys.stderr)
            return 1

if __name__ == "__main__":
    raise SystemExit(main())
