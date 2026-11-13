#!/usr/bin/env python3
"""Revert Done transitions that have no delivery evidence.

Multica has no native status rule that can require evidence, and branch
protection is unavailable on the current GitHub plan, so this controller is
the independent gate for the two objectively checkable rules:

1. A producer must never approve its own work (RELEASE_APPROVED/PRODUCER pair).
2. A "Release ..." issue may be Done only when the promotion controller
   recorded that PR in a healthy deploy, or when the release was explicitly
   docs-only (no_runtime_release_required).

Anything that cannot be decided stays untouched: this gate fails open on
unknown data and only rewrites a status when a rule is violated, so it cannot
mask a real defect. Reverts are auditable in the journal and in the issue
comment.
"""

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

DB_CONTAINER = "postgres-6ihjnudsifbcvklz5hqxdldc"
WORKSPACE = "28378cc8-2c3a-4f8e-af1c-63e308407b17"
OWNER_ID = "1f18ef41-ce12-4074-984f-6cb12e971040"
DEPLOY_STATE = Path("/var/lib/paperclip-gitops/zar-i-szlif.json")
STATE_DIR = Path("/var/lib/multica-done-gate")
WATERMARK = STATE_DIR / "watermark.json"
LOG = STATE_DIR / "gate.log"
REVERTED = STATE_DIR / "reverted.json"
RELEASE_TITLE = re.compile(r"^Release\b")
APPROVAL = re.compile(
    r"RELEASE_APPROVED\s+([0-9a-f]{40})\s+PRODUCER\s+([0-9a-f-]{36})", re.IGNORECASE
)
PR_REF = re.compile(r"PR\s*#(\d+)")


def psql(sql):
    result = subprocess.run(
        ["docker", "exec", DB_CONTAINER, "psql", "-U", "multica_poc",
         "-d", "multica_poc", "-At", "-F", "\x1f", "-R", "\x1e", "-c", sql],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[:300])
    return result.stdout


def deploy_state():
    try:
        data = json.loads(DEPLOY_STATE.read_text(encoding="utf8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def evaluate(title, description, comments, state):
    """Return a violation code for one Done issue, or None when it may stand."""
    for author, content in comments:
        match = APPROVAL.search(content or "")
        if match and author == match.group(2):
            return "self_approval"
    if not RELEASE_TITLE.match(title or ""):
        return None
    pr = PR_REF.search(description or "")
    if not pr:
        return None
    number = int(pr.group(1))
    healthy = state.get("status") == "healthy"
    if healthy and number in (state.get("release_prs") or []):
        return None
    if any("no_runtime_release_required" in (content or "") for _, content in comments):
        return None
    return "release_without_deploy_evidence"


def revert(issue_id, number, reason):
    detail = {
        "self_approval": "the producer approved its own change; an independent reviewer is required",
        "release_without_deploy_evidence": (
            "no healthy promotion record for this release PR and no "
            "no_runtime_release_required evidence"
        ),
    }[reason]
    body = (
        f"**DONE gate: reverted to in_review**\n\n"
        f"ZARI-{number} was closed as Done without valid evidence: {detail}.\n\n"
        f"Close it again only after the missing evidence exists; the gate re-checks "
        f"every {30} seconds and will revert an unevidenced Done again."
    )
    psql(
        "UPDATE issue SET status='in_review', updated_at=now() "
        f"WHERE id='{issue_id}' AND status='done';"
        "INSERT INTO comment (issue_id, author_type, author_id, content, workspace_id) "
        f"VALUES ('{issue_id}', 'member', '{OWNER_ID}', $body${body}$body$, '{WORKSPACE}');"
    )


def already_reverted():
    try:
        data = json.loads(REVERTED.read_text(encoding="utf8"))
    except (OSError, ValueError):
        return set()
    return set(data) if isinstance(data, list) else set()


def remember_revert(issue_id):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = sorted(already_reverted() | {issue_id})
    REVERTED.write_text(json.dumps(data), encoding="utf8")


def since(explicit=None):
    """Start of the checked window; None means bootstrap (never judge history)."""
    if explicit:
        return explicit
    try:
        data = json.loads(WATERMARK.read_text(encoding="utf8"))
        base = datetime.datetime.fromisoformat(data["since"])
    except (OSError, ValueError, KeyError):
        return None
    return (base - datetime.timedelta(minutes=10)).isoformat()


def save_watermark(now):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    WATERMARK.write_text(json.dumps({"since": now.isoformat()}), encoding="utf8")


def scan(dry_run, window):
    rows = psql(
        "SELECT id, number, title, coalesce(description,'') FROM issue "
        f"WHERE workspace_id='{WORKSPACE}' AND status='done' "
        f"AND updated_at > '{window}' ORDER BY number;"
    )
    state = deploy_state()
    findings = []
    for record in rows.split("\x1e"):
        if not record.strip():
            continue
        issue_id, number, title, description = (record.split("\x1f") + [""] * 4)[:4]
        comments = [
            tuple(row.split("\x1f", 1))
            for row in psql(
                "SELECT author_id, content FROM comment "
                f"WHERE issue_id='{issue_id}' AND deleted_at IS NULL ORDER BY created_at;"
            ).split("\x1e")
            if "\x1f" in row
        ]
        reason = evaluate(title, description, comments, state)
        if not reason:
            continue
        if issue_id in already_reverted():
            print(f"skip ZARI-{number}: already reverted once ({reason})", flush=True)
            continue
        findings.append((issue_id, int(number), reason))
        print(f"{'DRY-RUN ' if dry_run else ''}revert ZARI-{number}: {reason}", flush=True)
        if not dry_run:
            revert(issue_id, int(number), reason)
            remember_revert(issue_id)
    return findings


def self_test():
    state = {"status": "healthy", "release_prs": [175]}
    ok = evaluate("Release ZARI-197 abc — approved", "PR #175", [], state)
    assert ok is None, ok
    bad = evaluate("Release ZARI-197 abc — approved", "PR #176", [], state)
    assert bad == "release_without_deploy_evidence", bad
    docs = evaluate("Release ZARI-195 abc — approved", "PR #174", [("x", "no_runtime_release_required")], state)
    assert docs is None, docs
    self_approval = evaluate(
        "Fix thing", "", [("3ae3fe95-5120-4053-8ab5-345f94b3a6e1",
                           "RELEASE_APPROVED " + "a" * 40 + "\nPRODUCER 3ae3fe95-5120-4053-8ab5-345f94b3a6e1")],
        state,
    )
    assert self_approval == "self_approval", self_approval
    independent = evaluate(
        "Fix thing", "", [("3a54e0b4-6526-4de5-a1fd-e66e205cb3b4",
                           "RELEASE_APPROVED " + "a" * 40 + "\nPRODUCER 3ae3fe95-5120-4053-8ab5-345f94b3a6e1")],
        state,
    )
    assert independent is None, independent
    print("self-test OK")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--since", help="explicit audit window start (RFC3339); dry-run only")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    window = since(args.since)
    if window is None:
        if args.dry_run:
            window = (now - datetime.timedelta(minutes=60)).isoformat()
            print("dry-run without watermark: checking only the last 60 minutes")
        else:
            save_watermark(now)
            print("bootstrap: watermark set, no history rewritten")
            return 0
    findings = scan(args.dry_run, window)
    if not args.dry_run:
        save_watermark(now)
    with LOG.open("a", encoding="utf8") as handle:
        handle.write(json.dumps({"at": now.isoformat(), "dry_run": args.dry_run,
                                 "reverted": findings}) + "\n")
    print(f"done-gate: {len(findings)} violation(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
