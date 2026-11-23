#!/usr/bin/env python3
"""Read-only, fail-closed native Multica approval check for production release.

A deployment controller must FIRST independently verify the GitHub merged PR,
exact head/merge SHAs and required CI. This module verifies the real persisted
Multica reviewer comment, reviewer task identity, producer task identity and
issue state (done or in_review); it never deploys.
"""
import argparse
from pathlib import Path
from datetime import datetime
import json
import os
import re
import subprocess
import sys

ALLOWED_REPOS = {"jtrtdhrst/harness-zar-i-szlif", "jtrtdhrst/zar-i-szlif"}
WORKSPACE = "28378cc8-2c3a-4f8e-af1c-63e308407b17"
REVIEWERS = {
    "3a54e0b4-6526-4de5-a1fd-e66e205cb3b4",  # independent CTO only
}
SHA = re.compile(r"^[a-f0-9]{40}$")
ISSUE_REF = re.compile(r"^[A-Z][A-Z0-9]*-([0-9]{1,7})$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}$")


class Denied(Exception):
    pass

# Release fail-closed security HOLD: independent of workflow issue status.
# Persisted as reviewed main source and independently corroborated with live
# Multica issue metadata. Never infer a cleared hold from a status transition.
SECURITY_HOLD_FILE = Path(__file__).with_name("security-hold.json")
SECURITY_HOLD_ISSUE = "01a1e0ac-5d9e-7c46-8add-67be5ff69dcc"
SECURITY_HOLD_OWNER = "1f18ef41-ce12-4074-984f-6cb12e971040"


def _iso_time(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


SECURITY_HOLD_CTO = "3a54e0b4-6526-4de5-a1fd-e66e205cb3b4"
SECURITY_HOLD_COO = "774ab8a9-4e60-42a1-af03-c1c09860c15f"


def _read_clearance_comment(value, db_container, actor_type, actor_id, expected_content):
    if not isinstance(value, str) or not UUID.fullmatch(value):
        raise Denied("security_hold_evidence_id_invalid")
    sql = ("SELECT row_to_json(t)::text FROM (SELECT author_type, author_id, "
           "content, source_task_id FROM comment "
           f"WHERE id='{value}' AND issue_id='{SECURITY_HOLD_ISSUE}' "
           "AND deleted_at IS NULL) t")
    rows = read_rows(sql, db_container)
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise Denied("security_hold_evidence_comment_missing")
    item = rows[0]
    content = item.get("content")
    if (item.get("author_type") != actor_type or item.get("author_id") != actor_id
            or not isinstance(content, str)
            or content not in (expected_content, expected_content + "\n")):
        raise Denied("security_hold_evidence_comment_untrusted")
    if actor_type == "agent":
        task = task_record(item.get("source_task_id"), db_container)
        if (task.get("agent_id") != actor_id or task.get("issue_id") != SECURITY_HOLD_ISSUE
                or task.get("status") != "completed"):
            raise Denied("security_hold_evidence_run_not_completed")
    return True


def enforce_persistent_security_hold(db_container, hold_path=None):
    path = Path(hold_path) if hold_path is not None else SECURITY_HOLD_FILE
    if path.is_symlink() or not path.is_file():
        raise Denied("security_hold_record_missing")
    try:
        st = path.stat()
        gate_st = Path(__file__).stat()
    except OSError:
        raise Denied("security_hold_record_unreadable") from None
    # Authored repository checkout or root-owned production installation must
    # own BOTH checker and record, be non-group/world writable and single-link.
    if st.st_uid != gate_st.st_uid or st.st_nlink != 1 or (st.st_mode & 0o022):
        raise Denied("security_hold_record_unsafe_permissions")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise Denied("security_hold_record_unreadable") from None
    if not isinstance(record, dict):
        raise Denied("security_hold_record_invalid")
    if (record.get("schema_version") != 1
            or record.get("owner") != SECURITY_HOLD_OWNER
            or not isinstance(record.get("reason"), str)
            or not record["reason"].strip()
            or not _iso_time(record.get("activated_at"))
            or record.get("clearing_authority") != "workspace_owner_and_independent_CTO_COO"):
        raise Denied("security_hold_record_invalid")
    if record.get("active") is True:
        raise Denied("security_hold_active")
    if record.get("active") is not False:
        raise Denied("security_hold_not_explicitly_cleared")
    clearance = record.get("clearance")
    if not isinstance(clearance, dict):
        raise Denied("security_hold_clearance_missing")
    if clearance.get("cleared_by") != SECURITY_HOLD_OWNER or not _iso_time(clearance.get("cleared_at")):
        raise Denied("security_hold_clearance_not_authorized")
    sha = clearance.get("ctocoo_review_sha")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise Denied("security_hold_independent_review_missing")

    # Live metadata survives status changes. A source-only clearance can NEVER
    # bypass the active ZARI-213 hold in the authoritative Multica database.
    sql = ("SELECT row_to_json(t)::text FROM (SELECT metadata FROM issue "
           f"WHERE id='{SECURITY_HOLD_ISSUE}' AND workspace_id='{WORKSPACE}') t")
    rows = read_rows(sql, db_container)
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise Denied("security_hold_live_record_missing")
    meta = rows[0].get("metadata")
    if not isinstance(meta, dict) or meta.get("security_hold") is not False:
        raise Denied("security_hold_live_not_cleared")

    # Not arbitrary strings or an arbitrary 40-hex value: three persisted,
    # role-authenticated Multica comments are required. The CTO/COO evidence
    # is bound to the SAME reviewed security patch SHA. The release-specific
    # exact-head approval remains independently checked by verify() below.
    _read_clearance_comment(
        clearance.get("isolation_e2e_comment_id"), db_container, "member",
        SECURITY_HOLD_OWNER, (
            "ISOLATION_CLEARANCE " + sha + "\n"
            "HARNESS_OWN_REPO_PASS\n"
            "PRODUCT_OWN_REPO_PASS\n"
            "CROSS_REPO_DENIED\n"
            "ROLLBACK_PASS"))
    _read_clearance_comment(
        clearance.get("cto_review_comment_id"), db_container, "agent",
        SECURITY_HOLD_CTO, "CODE_ONLY_APPROVED " + sha)
    _read_clearance_comment(
        clearance.get("coo_authorization_comment_id"), db_container, "agent",
        SECURITY_HOLD_COO, "RELEASE_APPROVED " + sha)
    return True


def validate_input(repo, pr, head_sha, merge_sha, issue_ref):
    if repo not in ALLOWED_REPOS or not isinstance(pr, int) or pr < 1 or pr > 1000000:
        raise Denied("invalid_repository_or_pr")
    if not all(isinstance(x, str) and SHA.fullmatch(x) for x in (head_sha, merge_sha)):
        raise Denied("invalid_sha")
    if issue_ref is not None and not ISSUE_REF.fullmatch(issue_ref):
        raise Denied("invalid_issue_ref")


def query(repo, pr, issue_ref):
    if issue_ref is not None:
        number = int(ISSUE_REF.fullmatch(issue_ref).group(1))
        selector = f"i.number={number}"
    else:
        url = f"https://github.com/{repo}/pull/{pr}"
        selector = (
            "i.id IN (SELECT c.issue_id FROM comment c JOIN issue i2 ON i2.id=c.issue_id "
            f"WHERE c.deleted_at IS NULL AND c.content LIKE '%{url}%' AND i2.workspace_id='{WORKSPACE}')"
        )
    return f"""
SELECT row_to_json(t)::text FROM (
 SELECT i.id issue_id, i.number issue_number, i.status issue_status, i.description issue_description,
        i.assignee_id producer_id, i.title issue_title,
        (SELECT json_agg(json_build_object(
            'id', c.id, 'author_type', c.author_type, 'author_id', c.author_id,
            'content', c.content, 'created_at', c.created_at,
            'source_task_id', c.source_task_id) ORDER BY c.created_at DESC)
         FROM comment c WHERE c.issue_id=i.id AND c.deleted_at IS NULL\n           AND (c.content ILIKE '%RELEASE_APPROVED%'\n                OR c.content ILIKE '%CHANGES_REQUESTED%')) comments,
        (SELECT count(*) FROM agent_task_queue q
         WHERE q.issue_id=i.id AND q.agent_id=i.assignee_id AND q.status='completed') producer_runs
 FROM issue i
 WHERE i.workspace_id='{WORKSPACE}' AND {selector}
) t
"""


def read_rows(sql, db_container):
    if not CONTAINER.fullmatch(db_container):
        raise Denied("invalid_database_container")
    cmd = ["docker", "exec", db_container, "psql", "-U", "multica_poc", "-d", "multica_poc", "-At", "-c", sql]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Denied("database_unavailable") from None
    if result.returncode != 0 or len(result.stdout) > 180000:
        raise Denied("database_unavailable")
    try:
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    except (ValueError, TypeError):
        raise Denied("database_invalid_response") from None


def task_record(task_id, db_container):
    if not isinstance(task_id, str) or not UUID.fullmatch(task_id):
        raise Denied("invalid_reviewer_task")
    sql = (
        "SELECT row_to_json(t)::text FROM (SELECT id, agent_id, issue_id, status "
        "FROM agent_task_queue WHERE id='" + task_id + "') t"
    )
    rows = read_rows(sql, db_container)
    if len(rows) != 1:
        raise Denied("reviewer_task_missing")
    return rows[0]


def verify(row, repo, pr, head_sha, merge_sha, issue_ref, db_container):
    validate_input(repo, pr, head_sha, merge_sha, issue_ref)
    enforce_persistent_security_hold(db_container)
    if not isinstance(row, dict):
        raise Denied("missing_or_ambiguous_issue")
    if row.get("issue_status") not in ("done", "in_review"):
        raise Denied("issue_not_reviewable")
    if issue_ref is not None and row.get("issue_number") != int(ISSUE_REF.fullmatch(issue_ref).group(1)):
        raise Denied("issue_reference_mismatch")
    # A task number alone does not bind an issue to the canonical repository
    # and PR: independently validate the issue's owner-authored description.
    expected_url = f"https://github.com/{repo}/pull/{pr}"
    description = row.get("issue_description")
    if not isinstance(description, str) or not re.search(
        re.escape(expected_url) + r"(?![0-9])", description
    ):
        raise Denied("issue_pr_link_missing")
    producer = row.get("producer_id")
    if not isinstance(producer, str) or not UUID.fullmatch(producer):
        raise Denied("invalid_producer")
    if int(row.get("producer_runs") or 0) < 1:
        raise Denied("producer_run_missing")

    comments = row.get("comments")
    if not isinstance(comments, list) or not comments:
        raise Denied("missing_release_approval")

    pattern = re.compile(
        r"^\s*RELEASE_APPROVED\s+([a-f0-9]{40})\b.*?^\s*REPOSITORY\s+([a-z0-9_.-]+/[a-z0-9_.-]+)\s*$.*?^\s*PR\s+([0-9]+)\s*$.*?^\s*PRODUCER\s+([0-9a-f-]{36})\b",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    approval = None
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        match = pattern.search(str(comment.get("content") or ""))
        if not match:
            continue
        if match.group(1).lower() != head_sha.lower():
            continue
        if match.group(2).lower() != repo.lower() or int(match.group(3)) != pr:
            continue
        approval = (comment, match.group(1).lower(), match.group(4).lower())
        break
    if approval is None:
        raise Denied("missing_release_approval")

    comment, approved_sha, claimed_producer = approval
    reviewer = comment.get("author_id")
    if comment.get("author_type") != "agent" or reviewer not in REVIEWERS:
        raise Denied("reviewer_not_authorized")
    if claimed_producer != producer:
        raise Denied("producer_mismatch")
    if reviewer == producer:
        raise Denied("not_independent")

    reviewer_task = task_record(comment.get("source_task_id"), db_container)
    if reviewer_task.get("agent_id") != reviewer:
        raise Denied("reviewer_task_agent_mismatch")
    if reviewer_task.get("issue_id") != row.get("issue_id"):
        raise Denied("reviewer_task_issue_mismatch")
    if reviewer_task.get("status") != "completed":
        raise Denied("reviewer_task_not_completed")

    # A later changes-requested note on the same head revokes the approval.
    approval_time = str(comment.get("created_at") or "")
    for later in comments:
        if not isinstance(later, dict) or str(later.get("created_at") or "") <= approval_time:
            continue
        content = str(later.get("content") or "")
        if re.search(r"CHANGES_REQUESTED\s+" + re.escape(head_sha), content, re.IGNORECASE):
            raise Denied("changes_requested_after_approval")

    return {
        "verified": True,
        "repository": repo,
        "pr": pr,
        "head_sha": head_sha,
        "merge_sha": merge_sha,
        "issue_id": row.get("issue_id"),
        "issue_number": row.get("issue_number"),
        "issue_status": row.get("issue_status"),
        "reviewer_agent_id": reviewer,
        "producer_agent_id": producer,
        "reviewer_task_id": comment.get("source_task_id"),
        "approval_comment_id": comment.get("id"),
        "approved_head_sha": approved_sha,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify exact-SHA independent Multica release admission")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--merge-sha", required=True)
    parser.add_argument("--issue-ref", default=None)
    parser.add_argument("--db-container", default=os.environ.get("MULTICA_DB_CONTAINER", "postgres-6ihjnudsifbcvklz5hqxdldc"))
    args = parser.parse_args(argv)
    try:
        validate_input(args.repo, args.pr, args.head_sha, args.merge_sha, args.issue_ref)
        rows = read_rows(query(args.repo, args.pr, args.issue_ref), args.db_container)
        if len(rows) != 1:
            raise Denied("missing_or_ambiguous_issue")
        print(json.dumps(verify(rows[0], args.repo, args.pr, args.head_sha, args.merge_sha,
                                args.issue_ref, args.db_container), sort_keys=True))
        return 0
    except Denied as error:
        print(json.dumps({"verified": False, "reason": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
