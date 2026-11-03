#!/usr/bin/env python3
"""Strict, secret-free acceptance gate for a Hermes ↔ Paperclip run.

Usage: python3 verify_e2e.py --evidence evidence.json --expected-profile cho
No external SDK, no network access, no auto-approval or modifications.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Real named Hermes profiles, not bank IDs and not retired POC actors.
# Model/profile identity must agree with the authoritative Paperclip registry.
PRODUCTION_PROFILES = frozenset({
    "ceo", "cho", "cmo", "coo", "cpo", "cto", "designer",
    "email-creative", "engineer", "harness-engineer",
    "lifecycle-ops", "mascot-designer", "mcp-engineer", "ui-qa",
})

REQUIRED = {
    "paperclip_run_id": "Real Paperclip-owned Hermes run",
    "paperclip_issue_id": "Issue owning the Paperclip run",
    "executing_agent_id": "Paperclip agent owning the run",
    "paperclip_trace_id": "Paperclip project trace for the run",
    "hermes_run_id": "Hermes run created by the adapter",
    "named_profile": "The explicitly expected Hermes profile, not default",
    "profile_auth_test": "Authentication and cross-profile negative test",
    "run_scoped_mcp_bridge": "Private run-bound MCP credential and denial tests",
    "wiki_tool_call": "Real Paperclip Named MCP tools/call read",
    "published_skill": "Read of a versioned published skill",
    "hindsight": "Native separate-session retain/recall and isolation",
    "opik_trace": "Trace correlated with the exact Paperclip run",
    "failed_early_auth": "Separate correlated early-auth rejection attempt",
    "release": "Deployed SHA/digest and rollback result",
    "review": "Independent, explicit review and approval",
}


def validate(data: dict, expected_profile: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Evidence root must be a JSON object"]
    if expected_profile not in PRODUCTION_PROFILES:
        errors.append("expected profile is not one of the 14 real named Hermes profiles")
    if data.get("named_profile") not in PRODUCTION_PROFILES:
        errors.append("named_profile is not a registered real agent profile")
    if data.get("named_profile") != expected_profile:
        errors.append("named_profile does not match --expected-profile")
    run = data.get("paperclip_run_id")
    if not isinstance(run, str) or len(run) < 12:
        errors.append("paperclip_run_id missing or invalid")
    for field in ("paperclip_issue_id", "executing_agent_id", "paperclip_trace_id", "hermes_run_id", "named_profile"):
        if not isinstance(data.get(field), str) or not data[field]:
            errors.append(f"{field} missing or invalid")
    for item in REQUIRED:
        if item not in data:
            errors.append(f"missing: {item}")
    if data.get("secrets_exposed") is not False:
        errors.append("secrets_exposed must explicitly be false")

    steps = {
        "profile_auth_test": ("passed", "wrong_profile_rejected", "dedicated_key_stored_as_secret_ref"),
        "run_scoped_mcp_bridge": (
            "passed",
            "paperclip_token_bound_to_run",
            "agent_id_verified",
            "wrong_run_rejected",
            "wrong_agent_rejected",
            "missing_credential_rejected",
            "revoked_on_completion",
            "secret_not_logged_or_prompted",
        ),
        "wiki_tool_call": ("passed", "paperclip_agent_run_context", "actual_content_read"),
        "published_skill": ("passed", "version_verified"),
        "hindsight": ("passed", "later_session_recalled", "cross_bank_isolation"),
        "opik_trace": ("passed", "run_id_correlated", "model_and_usage_spans"),
        "release": ("passed", "sha_verified", "rollback_tested"),
        "review": ("passed", "independent_reviewer", "approved"),
    }
    for step, fields in steps.items():
        value = data.get(step)
        if not isinstance(value, dict):
            errors.append(f"{step}: expected object")
            continue
        for field in fields:
            if value.get(field) is not True:
                errors.append(f"{step}.{field}: not verified")
    wiki = data.get("wiki_tool_call", {})
    if isinstance(wiki, dict):
        if wiki.get("http_status") != 200:
            errors.append("wiki_tool_call.http_status must be 200")
        if not wiki.get("invocation_id"):
            errors.append("wiki_tool_call.invocation_id missing")
    trace = data.get("opik_trace", {})
    if isinstance(trace, dict):
        if not trace.get("trace_id"):
            errors.append("opik_trace.trace_id missing")
        for field, root_field in (
            ("paperclip_run_id", "paperclip_run_id"),
            ("paperclip_issue_id", "paperclip_issue_id"),
            ("paperclip_agent_id", "executing_agent_id"),
            ("paperclip_trace_id", "paperclip_trace_id"),
            ("hermes_run_id", "hermes_run_id"),
        ):
            if trace.get(field) != data.get(root_field):
                errors.append(f"opik_trace.{field} mismatch")
    failed_auth = data.get("failed_early_auth", {})
    if isinstance(failed_auth, dict):
        if failed_auth.get("rejected") is not True:
            errors.append("failed_early_auth.rejected must be true")
        if failed_auth.get("http_status") not in (401, 403):
            errors.append("failed_early_auth.http_status must be 401 or 403")
        if failed_auth.get("hermes_run_id") is not None:
            errors.append("failed_early_auth.hermes_run_id must be absent before run admission")
        if not failed_auth.get("attempt_id") or failed_auth.get("attempt_id") == run:
            errors.append("failed_early_auth.attempt_id must identify a separate negative attempt")
        if not failed_auth.get("acceptance_suite_id"):
            errors.append("failed_early_auth.acceptance_suite_id missing")
        if not failed_auth.get("opik_trace_id"):
            errors.append("failed_early_auth.opik_trace_id missing")
        if failed_auth.get("paperclip_issue_id") != data.get("paperclip_issue_id"):
            errors.append("failed_early_auth.paperclip_issue_id mismatch")
        if failed_auth.get("paperclip_agent_id") != data.get("executing_agent_id"):
            errors.append("failed_early_auth.paperclip_agent_id mismatch")
        # This offline structural verifier cannot authenticate user-authored JSON or
        # fetch Paperclip/Opik records. Never describe its result as acceptance proof.
    errors.append("offline verifier cannot retrieve/authenticate source records; acceptance remains UNVERIFIED")
    skill = data.get("published_skill", {})
    if isinstance(skill, dict) and not skill.get("version_id"):
        errors.append("published_skill.version_id missing")
    release = data.get("release", {})
    if isinstance(release, dict) and not release.get("immutable_digest_or_sha"):
        errors.append("release.immutable_digest_or_sha missing")
    review = data.get("review", {})
    if isinstance(review, dict) and review.get("reviewer_agent_id") == data.get("executing_agent_id"):
        errors.append("review must be independent of executor")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--expected-profile", required=True)
    args = parser.parse_args()
    try:
        doc = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"BLOCKED: cannot read evidence: {exc}", file=sys.stderr)
        return 2
    problems = validate(doc, args.expected_profile)
    if problems:
        print(f"BLOCKED ({len(problems)} failed conditions):")
        for item in problems:
            print(f" - {item}")
        return 1
    print("STRUCTURAL PASS; authoritative source readbacks remain UNVERIFIED")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
