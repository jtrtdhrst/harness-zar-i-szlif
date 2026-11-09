#!/usr/bin/env python3
"""Product release admission: native Paperclip approval -> exact SHA -> Coolify.

Uses only the existing Coolify GitHub App installation. No PAT, no new app,
no branch force push. The existing GitHub Actions production promotion must
be disabled before this controller is enabled. Fails closed on any ambiguity.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

REPO = "miloszspyrka-code/zar-i-szlif"
APP_ID = 5398752
INSTALL_ID = 173456397
RELEASE_REF = "ci-approved"
ROOT = Path("/var/lib/paperclip-gitops")
STATE = ROOT / "zar-i-szlif.json"
LOCK = ROOT / "zar-i-szlif.lock"
NATIVE_GATE = Path("/usr/local/libexec/paperclip_native_release_gate.py")
PUBLIC_RELEASE = "https://panel.zariszlif.pl/__release.json"
PUBLIC_HEALTH = "https://panel.zariszlif.pl/healthz"
SHA = re.compile(r"^[a-f0-9]{40}$")


# Exact exception for the already-merged RepoWise knowledge migration (#164).
# These two files are CI coverage metadata, NOT application/runtime outputs.
# No future commit inherits this exception, even if it changes the same paths.
LEGACY_KNOWLEDGE_SHA = "81c4b068b89f4c035098c6c9107f755f56919a87"
LEGACY_KNOWLEDGE_PR = 164
LEGACY_CI_ONLY_FILES = frozenset({"scripts/ci-path-coverage.mjs", "tests/ci-path-coverage.test.mjs"})

class Denied(Exception):
    pass


def run(argv, timeout=30, allow_fail=False):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        raise Denied("execution_unavailable") from None
    if result.returncode != 0 and not allow_fail:
        raise Denied("controlled_command_failed")
    return result


def github_api(path, method="get", body=None):
    """Existing installed App only. Never return or print installation token."""
    if not re.fullmatch(r"/repos/miloszspyrka-code/zar-i-szlif/[A-Za-z0-9/_+.-]+", path):
        raise Denied("unsafe_github_resource")
    if method not in ("get", "patch"):
        raise Denied("unsafe_github_method")
    php = (
        '$app=App\\Models\\GithubApp::findOrFail(1);'
        'if((int)$app->app_id!==' + str(APP_ID) +
        '||(int)$app->installation_id!==' + str(INSTALL_ID) +
        '){throw new \\RuntimeException("wrong_app");}'
        '$token=generateGithubInstallationToken($app);'
        '$client=Illuminate\\Support\\Facades\\Http::GitHub($app->api_url,$token);'
    )
    path_literal = json.dumps(path)
    if method == "get":
        php += '$result=$client->get(' + path_literal + ');'
    else:
        # Only non-force, exact validated ref advancement is supported.
        if not isinstance(body, dict) or set(body) != {"sha", "force"} or not SHA.fullmatch(str(body.get("sha"))) or body.get("force") is not False or path != "/repos/" + REPO + "/git/refs/heads/" + RELEASE_REF:
            raise Denied("invalid_ref_update")
        php += '$result=$client->patch(' + path_literal + ', json_decode(' + json.dumps(json.dumps(body)) + ', true));'
    php += 'echo json_encode(["http"=>$result->status(),"data"=>$result->json()]);'
    result = run(["docker", "exec", "coolify", "php", "artisan", "tinker", "--execute=" + php], timeout=40)
    try:
        data = json.loads(result.stdout.strip())
    except (ValueError, TypeError):
        raise Denied("github_invalid_json") from None
    if data.get("http") not in (200, 201):
        raise Denied("github_http_" + str(data.get("http")))
    return data.get("data")


def ref(branch):
    if branch not in ("main", RELEASE_REF):
        raise Denied("invalid_release_branch")
    obj = github_api("/repos/" + REPO + "/git/ref/heads/" + branch)
    sha = (obj or {}).get("object", {}).get("sha")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise Denied("invalid_ref_sha")
    return sha


def commit(sha):
    if not SHA.fullmatch(sha):
        raise Denied("invalid_commit_sha")
    obj = github_api("/repos/" + REPO + "/commits/" + sha)
    if not isinstance(obj, dict) or obj.get("sha") != sha:
        raise Denied("invalid_commit")
    return obj


def provenance(merge_sha):
    """Exactly one merged main PR with this exact recorded merge commit."""
    candidates = github_api("/repos/" + REPO + "/commits/" + merge_sha + "/pulls")
    if not isinstance(candidates, list):
        raise Denied("pr_mapping_unreadable")
    matched = [x for x in candidates if isinstance(x, dict)
               and x.get("merge_commit_sha") == merge_sha
               and x.get("merged_at")
               and isinstance(x.get("base"), dict)
               and x["base"].get("ref") == "main"]
    if len(matched) != 1:
        raise Denied("missing_or_ambiguous_main_pr")
    pr = matched[0]
    number = pr.get("number")
    head = (pr.get("head") or {}).get("sha")
    if not isinstance(number, int) or number < 1 or not isinstance(head, str) or not SHA.fullmatch(head):
        raise Denied("invalid_pr_identity")
    return number, head


def checks(sha):
    obj = github_api("/repos/" + REPO + "/commits/" + sha + "/check-runs")
    checks = (obj or {}).get("check_runs")
    total = (obj or {}).get("total_count")
    if not isinstance(checks, list) or not isinstance(total, int) or total != len(checks) or total > 100:
        raise Denied("checks_incomplete")
    matches = [x for x in checks if x.get("name") == "validate-product"]
    if len(matches) != 1 or matches[0].get("status") != "completed" or matches[0].get("conclusion") != "success":
        raise Denied("product_ci_not_green")
    if any(x.get("status") != "completed" or x.get("conclusion") not in ("success", "skipped", "neutral") for x in checks):
        raise Denied("nonpassing_checks")


def native_approval(pr, head_sha, merge_sha):
    if not NATIVE_GATE.is_file():
        raise Denied("native_gate_not_installed")
    r = run([sys.executable, str(NATIVE_GATE),
             "--repo", REPO, "--pr", str(pr),
             "--head-sha", head_sha, "--merge-sha", merge_sha], timeout=35, allow_fail=True)
    if r.returncode != 0:
        raise Denied("native_approval_unverified")


def non_runtime_files_only(pr_number, commit_sha, node):
    """True only when all PR files are non-runtime docs/metadata changes.

    Incomplete GitHub file pagination, renames, or any unfamiliar code path
    must never be classified as safe-to-skip. The legacy CI-only exception
    is tied to one immutable commit and one merged PR.
    """
    files = node.get("files")
    if not isinstance(files, list) or not files or len(files) >= 200:
        raise Denied("commit_file_inventory_unavailable_or_truncated")
    for file in files:
        if not isinstance(file, dict) or file.get("status") not in ("added", "modified", "removed"):
            return False
        name = file.get("filename")
        if not isinstance(name, str) or not name or "/../" in name:
            return False
        if name.startswith(("docs/", ".repowise/")):
            continue
        if (pr_number == LEGACY_KNOWLEDGE_PR
                and commit_sha == LEGACY_KNOWLEDGE_SHA
                and name in LEGACY_CI_ONLY_FILES):
            continue
        return False
    return True


def candidate_history(release_sha, main_sha):
    """Walk first-parent main history and verify *every* new merged PR."""
    if release_sha == main_sha:
        return []
    current = main_sha
    pending = []
    seen = set()
    for _ in range(50):
        if current == release_sha:
            return list(reversed(pending))
        if current in seen:
            raise Denied("history_cycle")
        seen.add(current)
        node = commit(current)
        parents = node.get("parents")
        # A squash is valid only if GitHub maps this exact merge SHA to
        # one merged PR. Direct commits, rebases and ambiguous PRs fail closed.
        if not isinstance(parents, list) or len(parents) not in (1, 2):
            raise Denied("invalid_main_commit_parent_count")
        first = parents[0].get("sha")
        if not isinstance(first, str) or not SHA.fullmatch(first):
            raise Denied("invalid_first_parent")
        pr, head = provenance(current)
        checks(head)
        checks(current)
        # Docs-only squash PRs are NOT releases and do not require a Paperclip
        # runtime work product. Everything else, including runtime squashes,
        # still requires the original independent native approval gate.
        if len(parents) == 1 and non_runtime_files_only(pr, current, node):
            current = first
            continue
        native_approval(pr, head, current)
        pending.append({"pr": pr, "head": head, "merge": current})
        current = first
    raise Denied("too_many_unreleased_merges")


def live_release():
    import urllib.request
    try:
        req = urllib.request.Request(PUBLIC_RELEASE, headers={"Cache-Control": "no-cache", "User-Agent": "PaperclipProductRelease/1"})
        with urllib.request.urlopen(req, timeout=12) as r:
            if r.status != 200:
                raise Denied("release_http_unhealthy")
            data = json.loads(r.read(4096))
        with urllib.request.urlopen(PUBLIC_HEALTH, timeout=12) as r:
            if r.status != 200:
                raise Denied("health_http_unhealthy")
    except (OSError, ValueError, TimeoutError):
        raise Denied("production_readback_unavailable") from None
    sha = data.get("commit")
    if not isinstance(sha, str) or not SHA.fullmatch(sha) or data.get("source") != "zar-i-szlif/main":
        raise Denied("production_provenance_invalid")
    return sha


def save(data):
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = STATE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        os.chmod(tmp, 0o600)
        json.dump(data, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE)


def process(plan=False):
    current = ref("main")
    release = ref(RELEASE_REF)
    live = live_release()
    if live != release:
        raise Denied("production_not_at_current_release_ref")
    if current == release:
        return {"result":"already_released", "sha":current,"live":live}
    verified = candidate_history(release, current)
    if not verified:
        # Main only advanced through independently verified documentation PRs.
        # No Docker build, no branch advancement and no production deployment.
        return {"result": "no_runtime_release_required", "main": current,
                "release_ref": release, "live": live}
    if ref("main") != current or ref(RELEASE_REF) != release:
        raise Denied("git_ref_race")
    summary = {"main":current,"prior":release,"reviewed_prs":[x["pr"] for x in verified]}
    if plan:
        return {"result":"admissible", **summary}
    github_api("/repos/" + REPO + "/git/refs/heads/" + RELEASE_REF, method="patch", body={"sha":current,"force":False})
    if ref(RELEASE_REF) != current:
        raise Denied("release_ref_readback_mismatch")
    # Coolify already autodeploys only from ci-approved. Await exact artifact,
    # but never force-rewind a Git ref on failure; preserve evidence for safe
    # image rollback through Coolify's managed rollback facility.
    for _ in range(24):
        try:
            if live_release() == current:
                save({"last_deployed_sha":current,"previous_sha":release,"release_prs":summary["reviewed_prs"],"status":"healthy"})
                return {"result":"deployed","sha":current,"prior":release,"verified_prs":summary["reviewed_prs"],"healthy":True}
        except Denied:
            pass
        time.sleep(10)
    save({"pending_sha":current,"previous_sha":release,"status":"readback_failed_rollback_required"})
    raise Denied("deployment_readback_failed_rollback_required")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        raise SystemExit("requires root on approved host")
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(LOCK, "a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            result=process(plan=args.plan)
            print(json.dumps(result,sort_keys=True))
            return 0
        except Denied as exc:
            print(json.dumps({"result":"denied","reason":str(exc)}),file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
