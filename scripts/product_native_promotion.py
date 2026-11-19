#!/usr/bin/env python3
"""Product release admission: native Multica approval -> exact SHA -> Coolify.

Uses only the existing Coolify GitHub App installation. No PAT, no new app,
no branch force push. The existing GitHub Actions production promotion must
be disabled before this controller is enabled. Fails closed on any ambiguity.

When GitHub refuses to start a job for an account billing block, the green
check-run predicate can never be satisfied. That case is not a pass and not a
test failure: it is "CI never executed", proven from the check-run timing and
its billing annotation, and it is then satisfied only by the root-owned
exact-SHA local CI attestation of the reviewed head while that head's git tree
is byte-identical to the merged commit's tree. Independent native approval is
never replaced by that attestation.
"""
import argparse
import errno
import fcntl
import json
import os
from datetime import datetime
from pathlib import Path
import re
import stat
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
LOCAL_CI_DIR = ROOT / "local-ci"
NATIVE_GATE = Path("/usr/local/libexec/multica_native_release_gate.py")
PUBLIC_RELEASE = "https://panel.zariszlif.pl/__release.json"
PUBLIC_HEALTH = "https://panel.zariszlif.pl/healthz"
SHA = re.compile(r"^[a-f0-9]{40}$")
# GitHub refuses to start a job for an account billing block. That is not a
# test failure and not a pass: it is "CI never executed". Only this exact
# annotation text, on a job that ran for seconds, may be treated that way.
BILLING_BLOCKED = re.compile(
    r"recent account payments have failed|spending limit needs to be increased", re.IGNORECASE)
MAX_NEVER_STARTED_SECONDS = 120
TRUSTED_ATTESTATION_RUNNER = "zis-local-build"
TRUSTED_ATTESTATION_SOURCE = "product_local_ci"
# Attestation trust boundary: written only by product-local-ci-attest.service as
# User=root into a root:root 0700 tree. Owner/group and mode are part of the
# evidence, not decoration - a non-root writer could otherwise forge a pass.
ATTESTATION_UID = 0
ATTESTATION_GID = 0
FORBIDDEN_WRITE_BITS = 0o022  # group write | other write
ATTESTATION_MAX_BYTES = 8192



# Exact exception for the already-merged RepoWise knowledge migration (#164).
# These two files are CI coverage metadata, NOT application/runtime outputs.
# No future commit inherits this exception, even if it changes the same paths.
LEGACY_KNOWLEDGE_SHA = "81c4b068b89f4c035098c6c9107f755f56919a87"
LEGACY_KNOWLEDGE_PR = 164
LEGACY_CI_ONLY_FILES = frozenset({"scripts/ci-path-coverage.mjs", "tests/ci-path-coverage.test.mjs"})


# An immutable, independently reviewed CI-only source change. This fixes the
# PR183 staging deadlock without allowing arbitrary workflow edits or future PR
# heads to evade runtime release admission. It can never deploy an application.
CI_ONLY_REVIEWED_PR = 183
CI_ONLY_REVIEWED_HEAD = "62d879b2f2ad2cd1bec8758852b14e28848d813b"
CI_ONLY_REVIEWED_FILES = {
    ".github/workflows/product-ci.yml": "modified",
    "ops/coolify/Dockerfile.ci": "added",
    "tests/ci-path-coverage.test.mjs": "modified",
    "tests/test_release_promotion_contract.py": "modified",
}

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


GITHUB_PATH = re.compile(
    r"^/repos/miloszspyrka-code/zar-i-szlif/[A-Za-z0-9/_+.-]+$")
# Pagination query is allowed only on the check-run annotations resource.
GITHUB_ANNOTATIONS_PATH = re.compile(
    r"^/repos/miloszspyrka-code/zar-i-szlif/check-runs/[0-9]{1,20}/annotations"
    r"(\?per_page=[0-9]{1,3}(&page=[0-9]{1,5})?)?$")
ANNOTATIONS_PAGE_SIZE = 100
ANNOTATIONS_MAX_PAGES = 20
ANNOTATIONS_MAX_TOTAL = 2000


def github_api(path, method="get", body=None):
    """Existing installed App only. Never return or print installation token."""
    if not (GITHUB_PATH.fullmatch(path) or GITHUB_ANNOTATIONS_PATH.fullmatch(path)):
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


def _annotation_key(note):
    """Identity of one annotation, used to detect repeating/overlapping pages."""
    return (str(note.get("path", "")), str(note.get("start_line", "")),
            str(note.get("annotation_level", "")), str(note.get("message", "")))


def _annotations(check_run_id):
    """Every annotation of one check run, across all result pages.

    The GitHub annotations endpoint is paginated, so one response is not the
    whole truth: a later page can carry the non-billing failure that
    disqualifies a "never started" classification. Pages are consumed until a
    short page arrives; a malformed, repeating, overlapping, erroring or
    unbounded page set fails closed instead of being treated as complete.
    """
    if not isinstance(check_run_id, int):
        raise Denied("check_annotations_unreadable")
    base = "/repos/" + REPO + "/check-runs/" + str(check_run_id) + "/annotations"
    collected = []
    seen = set()
    seen_pages = set()
    for page in range(1, ANNOTATIONS_MAX_PAGES + 1):
        notes = github_api(base + "?per_page=" + str(ANNOTATIONS_PAGE_SIZE)
                           + "&page=" + str(page))
        if not isinstance(notes, list):
            raise Denied("check_annotations_unreadable")
        for note in notes:
            if not isinstance(note, dict) or not isinstance(note.get("message"), str):
                raise Denied("check_annotations_malformed")
        keys = {_annotation_key(note) for note in notes}
        fingerprint = tuple(sorted(keys))
        if notes and fingerprint in seen_pages:
            raise Denied("check_annotations_pagination_loop")
        seen_pages.add(fingerprint)
        if seen & keys:
            raise Denied("check_annotations_pagination_inconsistent")
        seen |= keys
        collected.extend(notes)
        if len(collected) > ANNOTATIONS_MAX_TOTAL:
            raise Denied("check_annotations_pagination_incomplete")
        if len(notes) < ANNOTATIONS_PAGE_SIZE:
            return collected
    raise Denied("check_annotations_pagination_incomplete")


def never_started_billing_blocked(run):
    """True only for a job GitHub refused to start because of account billing.

    A real test failure annotates its own reason ("Process completed with exit
    code 1", failing step, ...), so anything that is not the exact billing
    annotation, or that actually ran for a real amount of time, is not excused.
    """
    if run.get("status") != "completed" or run.get("conclusion") != "failure":
        return False
    started, finished = run.get("started_at"), run.get("completed_at")
    if not isinstance(started, str) or not isinstance(finished, str):
        return False
    try:
        elapsed = (datetime.fromisoformat(finished.replace("Z", "+00:00"))
                   - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds()
    except ValueError:
        return False
    if elapsed < 0 or elapsed > MAX_NEVER_STARTED_SECONDS:
        return False
    failures = [x for x in _annotations(run.get("id"))
                if isinstance(x, dict) and x.get("annotation_level") == "failure"]
    if not failures:
        return False
    return all(BILLING_BLOCKED.search(str(x.get("message", ""))) for x in failures)


def checks(sha):
    """Every check must pass; a billing-blocked job is "CI never executed".

    Returns the CI evidence actually relied upon, so the caller can demand the
    root-owned exact-SHA local CI attestation instead of silently treating a
    job that never ran as a pass.
    """
    obj = github_api("/repos/" + REPO + "/commits/" + sha + "/check-runs")
    checks = (obj or {}).get("check_runs")
    total = (obj or {}).get("total_count")
    if not isinstance(checks, list) or not isinstance(total, int) or total != len(checks) or total > 100:
        raise Denied("checks_incomplete")
    matches = [x for x in checks if x.get("name") == "validate-product"]
    if len(matches) != 1 or matches[0].get("status") != "completed":
        raise Denied("product_ci_not_green")
    product = matches[0]
    billed = False
    if product.get("conclusion") != "success":
        if not never_started_billing_blocked(product):
            raise Denied("product_ci_not_green")
        billed = True
    for check in checks:
        if check is product:
            continue
        if check.get("status") != "completed" or check.get("conclusion") not in ("success", "skipped", "neutral"):
            if not never_started_billing_blocked(check):
                raise Denied("nonpassing_checks")
            billed = True
    return {"billing_blocked": billed}


def _require_trusted_attestation_dir(info):
    """Directory that holds attestations must be root-owned and not writable
    by group or others; otherwise a non-root process could plant files."""
    if not stat.S_ISDIR(info.st_mode):
        raise Denied("local_ci_attestation_dir_untrusted")
    if info.st_uid != ATTESTATION_UID:
        raise Denied("local_ci_attestation_dir_untrusted")
    if info.st_mode & FORBIDDEN_WRITE_BITS:
        raise Denied("local_ci_attestation_dir_untrusted")


def _require_trusted_attestation_file(info):
    """One attestation inode: root-owned, single-link, regular, not writable
    by group/others and of bounded size."""
    if not stat.S_ISREG(info.st_mode):
        raise Denied("local_ci_attestation_not_regular")
    if info.st_uid != ATTESTATION_UID or info.st_gid != ATTESTATION_GID:
        raise Denied("local_ci_attestation_owner_untrusted")
    if info.st_mode & FORBIDDEN_WRITE_BITS:
        raise Denied("local_ci_attestation_mode_untrusted")
    if info.st_nlink != 1:
        raise Denied("local_ci_attestation_link_untrusted")
    if info.st_size > ATTESTATION_MAX_BYTES:
        raise Denied("local_ci_attestation_too_large")


def _secure_attestation_bytes(name):
    """Read one attestation file without following links, from validated inodes.

    Trust boundary: the only writer of this tree is root. The attest job runs
    as ``User=root`` (product-local-ci-attest.service) and its output directory
    ``/var/lib/paperclip-gitops`` is ``root:root 0700``. This consumer therefore
    accepts bytes only from a root-owned, root-group, single-link, regular file
    that is not group- or world-writable, reached through a directory descriptor
    that is itself root-owned and not group/world-writable.

    The bytes are read from the very descriptor that was validated, so a rename
    or replacement between check and read cannot substitute content (TOCTOU),
    and ``O_NOFOLLOW`` + the regular-file test mean a symlink or a FIFO is never
    opened as an attestation. A file that is group/world-writable, owned by
    anyone else, hard-linked, oversized or not a regular file is denied: those
    are the only ways a non-root process could plant or forge this evidence.
    """
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = str(LOCAL_CI_DIR)
    try:
        dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | nofollow)
    except OSError:
        raise Denied("local_ci_attestation_dir_unavailable") from None
    try:
        info = os.fstat(dir_fd)
        _require_trusted_attestation_dir(info)
        try:
            # O_NONBLOCK so a FIFO can never block the timer; it is rejected
            # by the regular-file check below instead.
            fd = os.open(name, os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0),
                         dir_fd=dir_fd)
        except FileNotFoundError:
            raise Denied("local_ci_attestation_missing") from None
        except OSError as error:
            if getattr(error, "errno", None) in (errno.ELOOP, errno.ENOTDIR):
                raise Denied("local_ci_attestation_symlink_denied") from None
            raise Denied("local_ci_attestation_unreadable") from None
        try:
            _require_trusted_attestation_file(os.fstat(fd))
            chunks = []
            total = 0
            while True:
                chunk = os.read(fd, 4096)
                if not chunk:
                    break
                total += len(chunk)
                if total > ATTESTATION_MAX_BYTES:
                    raise Denied("local_ci_attestation_too_large")
                chunks.append(chunk)
        finally:
            os.close(fd)
    finally:
        os.close(dir_fd)
    return b"".join(chunks)


def local_ci_attestation(sha):
    """Root-owned exact-SHA local CI attestation, used only for billing blocks.

    The file may substitute for GitHub check evidence only for the exact
    reviewed head commit, and only together with head/merge tree equality
    enforced by the caller. It never replaces the independent native approval.
    Shape checks below are necessary but not sufficient: the evidence is only
    as trustworthy as the file's ownership and mode, which are proven by
    _secure_attestation_bytes before any JSON is parsed.
    """
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise Denied("invalid_attestation_sha")
    raw = _secure_attestation_bytes(sha + ".json")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Denied("local_ci_attestation_unreadable") from None
    if not isinstance(data, dict):
        raise Denied("local_ci_attestation_unreadable")
    if data.get("sha") != sha:
        raise Denied("local_ci_attestation_sha_mismatch")
    if type(data.get("exit_code")) is not int or data["exit_code"] != 0:
        raise Denied("local_ci_attestation_not_green")
    if data.get("runner") != TRUSTED_ATTESTATION_RUNNER:
        raise Denied("local_ci_attestation_runner_untrusted")
    if data.get("source") != TRUSTED_ATTESTATION_SOURCE:
        raise Denied("local_ci_attestation_source_untrusted")
    if not isinstance(data.get("verified_at"), str) or not data["verified_at"]:
        raise Denied("local_ci_attestation_undated")
    return data


def premerge_rootless_attestation(sha, tree):
    """Only a root-owned exact-tree E2E receipt can replace absent PR checks."""
    if not isinstance(sha, str) or not SHA.fullmatch(sha) or not isinstance(tree, str) or not SHA.fullmatch(tree):
        raise Denied("invalid_premerge_identity")
    raw = _secure_attestation_bytes("premerge-" + sha + ".json")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Denied("premerge_attestation_unreadable") from None
    expected_stages = {
        "exact_tree": True, "rootless_isolation": True,
        "full_product_build": True, "network_none_validation": True,
        "final_image": True, "positive_provenance": True,
        "negative_versionless": True,
    }
    if (not isinstance(data, dict)
            or type(data.get("schema_version")) is not int
            or data["schema_version"] != 2
            or data.get("sha") != sha or data.get("tree") != tree
            or data.get("runner") != "zis-rootless-exact-tree"
            or data.get("source") != "root-verified-systemd-e2e"
            or type(data.get("exit_code")) is not int
            or data["exit_code"] != 0
            or not isinstance(data.get("stages"), dict)
            or set(data["stages"]) != set(expected_stages)
            or any(type(data["stages"][key]) is not bool
                   or data["stages"][key] is not True for key in expected_stages)
            or not isinstance(data.get("verified_at"), str)
            or not data["verified_at"]):
        raise Denied("premerge_attestation_invalid")
    return data


def premerge_head_checks(head_sha, merge_node):
    """No PR-controlled runner, no bypass of failing/pending GitHub checks."""
    try:
        return checks(head_sha)
    except Denied as error:
        if str(error) != "product_ci_not_green":
            raise
    try:
        runs = github_api("/repos/" + REPO + "/commits/" + head_sha + "/check-runs")
    except Denied:
        raise Denied("product_ci_not_green") from None
    if not isinstance(runs, dict) or runs.get("total_count") != 0 or runs.get("check_runs") != []:
        raise Denied("premerge_head_checkrun_not_empty")
    head_node = commit(head_sha)
    head_tree = (((head_node or {}).get("commit") or {}).get("tree") or {}).get("sha")
    merge_tree = (((merge_node or {}).get("commit") or {}).get("tree") or {}).get("sha")
    if not isinstance(head_tree, str) or not SHA.fullmatch(head_tree) or head_tree != merge_tree:
        raise Denied("head_merge_tree_mismatch")
    premerge_rootless_attestation(head_sha, head_tree)
    return {"billing_blocked": False, "rootless_premerge": True}


def issue_ref_from_pr(pr):
    """Bind native approval to the exact Multica issue identified by the merged PR."""
    doc = github_api("/repos/" + REPO + "/pulls/" + str(pr))
    if not isinstance(doc, dict) or type(doc.get("number")) is not int or doc["number"] != pr:
        raise Denied("pr_identity_unverified")
    title = doc.get("title")
    if not isinstance(title, str):
        raise Denied("missing_issue_ref")
    refs = set(re.findall(r"\b([A-Z][A-Z0-9]*-[0-9]{1,7})\b", title))
    if len(refs) != 1:
        raise Denied("missing_or_ambiguous_issue_ref")
    return refs.pop()


def native_approval(pr, head_sha, merge_sha):
    if not NATIVE_GATE.is_file():
        raise Denied("native_gate_not_installed")
    issue_ref = issue_ref_from_pr(pr)
    r = run([sys.executable, str(NATIVE_GATE),
             "--repo", REPO, "--pr", str(pr),
             "--head-sha", head_sha, "--merge-sha", merge_sha,
             "--issue-ref", issue_ref], timeout=35, allow_fail=True)
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



def reviewed_ci_only_pr(pr_number, head_sha, node):
    """Only the exact CTO-reviewed PR183 four-file CI patch may skip runtime.

    The caller still requires a trusted rootless exact-tree premerge receipt,
    green merged-main GitHub CI and a single-parent squash. No other PR or
    changed SHA inherits this exception; Docker runtime resources are untouched.
    """
    if pr_number != CI_ONLY_REVIEWED_PR or head_sha != CI_ONLY_REVIEWED_HEAD:
        return False
    files = node.get("files")
    if not isinstance(files, list) or len(files) != len(CI_ONLY_REVIEWED_FILES):
        return False
    found = {}
    for file in files:
        if not isinstance(file, dict):
            return False
        name, status = file.get("filename"), file.get("status")
        if not isinstance(name, str) or name in found or status not in ("added", "modified"):
            return False
        found[name] = status
    return found == CI_ONLY_REVIEWED_FILES

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
        head_ci = premerge_head_checks(head, node)
        merge_ci = checks(current)
        # Exact reviewed CI-only PR183 must never cause an unnecessary
        # application rollout. Unlike docs-only PRs this exceptional workflow
        # change requires a root-controlled, exact-tree, full rootless E2E
        # attestation BEFORE merge, plus GREEN main CI AFTER merge.
        if len(parents) == 1 and reviewed_ci_only_pr(pr, head, node):
            if (head_ci.get("rootless_premerge") is not True
                    or head_ci.get("billing_blocked")
                    or merge_ci.get("billing_blocked")):
                raise Denied("ci_only_rootless_proof_or_main_ci_missing")
            current = first
            continue
        # Docs-only squash PRs are NOT releases and do not require a Multica
        # runtime work product. Everything else, including runtime squashes,
        # still requires the original independent native approval gate.
        if len(parents) == 1 and non_runtime_files_only(pr, current, node):
            # Nothing here can reach a runtime artifact, but a job that never
            # ran is still not evidence: keep the strict rule for this path.
            if head_ci["billing_blocked"] or merge_ci["billing_blocked"] or head_ci.get("rootless_premerge"):
                raise Denied("product_ci_not_green")
            current = first
            continue
        evidence = "github_checks"
        if head_ci["billing_blocked"] or merge_ci["billing_blocked"]:
            # GitHub CI never executed for this repository (account billing
            # block). The sanctioned substitute is the root-owned exact-SHA
            # local CI attestation of the reviewed head, valid only while the
            # head tree is byte-identical to the merged commit's tree.
            local_ci_attestation(head)
            head_tree = ((commit(head) or {}).get("commit") or {}).get("tree", {}).get("sha")
            merge_tree = ((node or {}).get("commit") or {}).get("tree", {}).get("sha")
            if not isinstance(head_tree, str) or not isinstance(merge_tree, str) or head_tree != merge_tree:
                raise Denied("head_merge_tree_mismatch")
            evidence = "local_ci_attestation"
        if head_ci.get("rootless_premerge"):
            evidence = "rootless_premerge_attestation"
        native_approval(pr, head, current)
        pending.append({"pr": pr, "head": head, "merge": current, "ci_evidence": evidence})
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


def require_verified_local_image_delivery():
    """Never advance ci-approved before real runner/registry/deploy E2E."""
    ready = Path("/var/lib/paperclip-gitops/zis-image-promotion-ready.json")
    runner = Path("/opt/zis-actions-runner/.runner")
    if not runner.is_file() or not ready.is_file():
        raise Denied("local_image_delivery_unverified")
    try:
        data = json.loads(ready.read_text(encoding="utf8"))
    except (OSError, ValueError):
        raise Denied("local_image_delivery_unverified") from None
    expected = {"schema_version": 1, "verified": True,
                "registry": "127.0.0.1:5000",
                "coolify_image_app_uuid": "cs847jiwtuq5rlm8ntjeohgf",
                "runner": "zis-local-build"}
    if (not isinstance(data, dict)
            or any(type(data.get(k)) is not type(v) or data[k] != v
                   for k, v in expected.items())):
        raise Denied("local_image_delivery_unverified")


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
        return {"result":"admissible", "delivery_gate":"local_image_delivery_required", **summary}
    require_verified_local_image_delivery()
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
