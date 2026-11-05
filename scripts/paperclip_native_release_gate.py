#!/usr/bin/env python3
"""Read-only, fail-closed native Paperclip approval check for production release.

A deployment controller must FIRST independently verify GitHub merged PR,
exact head/merge SHAs and required CI. This module verifies real persisted
Paperclip reviewer, issue execution, candidate and run identity; never deploys.
"""
import argparse
import json
import os
import re
import subprocess
import sys

ALLOWED_REPOS = {"miloszspyrka-code/harness-zar-i-szlif", "miloszspyrka-code/zar-i-szlif"}
SHA = re.compile(r"[a-f0-9]{40}\Z")
CONTAINER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,126}\Z")

class Denied(Exception):
    pass

def validate_input(repo, pr, head_sha, merge_sha):
    if repo not in ALLOWED_REPOS or not isinstance(pr, int) or pr < 1 or pr > 1000000:
        raise Denied("invalid_repository_or_pr")
    if not all(isinstance(x, str) and SHA.fullmatch(x) for x in (head_sha, merge_sha)):
        raise Denied("invalid_sha")

def query(repo, pr):
    # Inputs validated against exact allowlist and integer bounds before SQL.
    return f"""
SELECT row_to_json(t)::text FROM (
 SELECT i.id::text issue_id, i.status issue_status,
   i.execution_state->>'status' execution_status,
   i.execution_state->>'lastDecisionOutcome' last_outcome,
   i.execution_state->>'lastDecisionId' last_decision_id,
   i.execution_state->'returnAssignee'->>'agentId' return_assignee,
   i.execution_state->'completedStageIds' completed_stage_ids,
   d.id::text decision_id, d.outcome decision_outcome,
   d.stage_id::text decision_stage_id, d.stage_type decision_stage_type,
   d.actor_agent_id::text reviewer_id, d.created_by_run_id::text reviewer_run_id,
   reviewer_run.agent_id::text reviewer_run_agent_id,
   reviewer_run.issue_id::text reviewer_run_issue_id,
   (SELECT COALESCE(json_agg(participant->>'agentId'),'[]'::json)
    FROM jsonb_array_elements(COALESCE(i.execution_policy->'stages','[]'::jsonb)) stage,
         jsonb_array_elements(COALESCE(stage->'participants','[]'::jsonb)) participant
    WHERE stage->>'id'=d.stage_id::text AND stage->>'type'='review'
      AND participant->>'type'='agent') eligible_reviewers,
   w.type work_product_type, w.provider, w.external_id, w.url,
   w.status product_status, w.review_state,
   w.metadata->>'headSha' head_sha,
   w.metadata->>'acceptedHeadSha' accepted_head_sha,
   w.metadata->>'paperclipReviewDecisionId' metadata_decision_id,
   w.metadata->>'mergeCommitSha' merge_commit_sha,
   w.created_by_run_id::text producer_run_id,
   producer.agent_id::text producer_agent_id,
   producer.issue_id::text producer_issue_id
 FROM issue_work_products w
 JOIN issues i ON i.id=w.issue_id
 LEFT JOIN issue_execution_decisions d ON d.id::text=i.execution_state->>'lastDecisionId'
 LEFT JOIN heartbeat_runs reviewer_run ON reviewer_run.id=d.created_by_run_id
 LEFT JOIN heartbeat_runs producer ON producer.id=w.created_by_run_id
 WHERE w.external_id='{repo}#{pr}'
) t
"""

def read_rows(repo, pr, db_container):
    if not CONTAINER.fullmatch(db_container):
        raise Denied("invalid_database_container")
    cmd = ["docker","exec",db_container,"psql","-U","paperclip","-d","paperclip","-At","-c",query(repo,pr)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Denied("database_unavailable") from None
    if result.returncode != 0 or len(result.stdout) > 180000:
        raise Denied("database_unavailable")
    try:
        return [json.loads(s) for s in result.stdout.splitlines() if s.strip()]
    except (ValueError, TypeError):
        raise Denied("database_invalid_response") from None

def verify(rows, repo, pr, head_sha, merge_sha):
    validate_input(repo, pr, head_sha, merge_sha)
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise Denied("missing_or_ambiguous_work_product")
    d = rows[0]
    if (d.get("external_id") != f"{repo}#{pr}" or
        d.get("url") != f"https://github.com/{repo}/pull/{pr}" or
        d.get("provider") != "github" or d.get("work_product_type") != "pull_request"):
        raise Denied("wrong_work_product")
    if (d.get("issue_status") != "done" or d.get("execution_status") != "completed" or
        d.get("last_outcome") != "approved" or d.get("decision_outcome") != "approved" or
        d.get("decision_stage_type") != "review"):
        raise Denied("native_review_not_approved")
    decision, reviewer, producer = d.get("decision_id"), d.get("reviewer_id"), d.get("producer_agent_id")
    issue_id, stage = d.get("issue_id"), d.get("decision_stage_id")
    if not all(isinstance(x,str) and x for x in (decision, reviewer, producer, issue_id, stage)):
        raise Denied("missing_identity")
    if decision != d.get("last_decision_id") or decision != d.get("metadata_decision_id"):
        raise Denied("decision_not_bound")
    if reviewer == producer or producer != d.get("return_assignee"):
        raise Denied("not_independent")
    if reviewer not in (d.get("eligible_reviewers") or []) or stage not in (d.get("completed_stage_ids") or []):
        raise Denied("stage_not_approved")
    if (not d.get("reviewer_run_id") or d.get("reviewer_run_agent_id") != reviewer or
        d.get("reviewer_run_issue_id") != issue_id):
        raise Denied("reviewer_run_mismatch")
    if not d.get("producer_run_id") or d.get("producer_issue_id") != issue_id:
        raise Denied("producer_run_mismatch")
    if d.get("product_status") != "merged" or d.get("review_state") != "approved":
        raise Denied("product_not_approved_and_merged")
    if d.get("head_sha") != head_sha or d.get("accepted_head_sha") != head_sha:
        raise Denied("head_sha_mismatch")
    if d.get("merge_commit_sha") != merge_sha:
        raise Denied("merge_sha_mismatch")
    return {"verified": True, "repository":repo, "pr":pr, "head_sha":head_sha, "merge_sha":merge_sha,
            "issue_id":issue_id, "decision_id":decision, "reviewer_agent_id":reviewer,
            "source_run_id":d["producer_run_id"]}

def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify exact-SHA independent Paperclip release admission")
    parser.add_argument("--repo",required=True)
    parser.add_argument("--pr",type=int,required=True)
    parser.add_argument("--head-sha",required=True)
    parser.add_argument("--merge-sha",required=True)
    parser.add_argument("--db-container",default=os.environ.get("PAPERCLIP_DB_CONTAINER","db-2omzqpy8dxgmhuwfbzo7bvvv"))
    a = parser.parse_args(argv)
    try:
        validate_input(a.repo,a.pr,a.head_sha,a.merge_sha)
        print(json.dumps(verify(read_rows(a.repo,a.pr,a.db_container),a.repo,a.pr,a.head_sha,a.merge_sha),sort_keys=True))
        return 0
    except Denied as exc:
        print(json.dumps({"verified":False,"reason":str(exc)}),file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
