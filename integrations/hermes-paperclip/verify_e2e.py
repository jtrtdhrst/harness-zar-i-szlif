#!/usr/bin/env python3
"""Strict, secret-free acceptance gate for Hermes ↔ Paperclip integration.

Usage: python3 verify_e2e.py --evidence evidence.json
No external SDK, no network access, no auto-approval or modifications.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED = {
    "paperclip_run_id": "Real Paperclip-owned Hermes Test run",
    "named_profile": "The invoked Hermes profile, not default",
    "profile_auth_test": "Authentication and cross-profile negative test",
    "wiki_tool_call": "Real Paperclip Named MCP tools/call read",
    "published_skill": "Read of a versioned published skill",
    "hindsight": "Native separate-session retain/recall and isolation",
    "opik_trace": "Trace correlated with the exact Paperclip run",
    "release": "Deployed SHA/digest and rollback result",
    "review": "Independent, explicit review and approval",
}
EXPECTED_PROFILE = "hermes-test"


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Evidence root must be a JSON object"]
    if data.get("named_profile") != EXPECTED_PROFILE:
        errors.append("named_profile must equal hermes-test")
    run = data.get("paperclip_run_id")
    if not isinstance(run, str) or len(run) < 12:
        errors.append("paperclip_run_id missing or invalid")
    for item in REQUIRED:
        if item not in data:
            errors.append(f"missing: {item}")
    if data.get("secrets_exposed") is not False:
        errors.append("secrets_exposed must explicitly be false")

    steps = {
        "profile_auth_test": ("passed", "wrong_profile_rejected", "dedicated_key_stored_as_secret_ref"),
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
        if run and trace.get("paperclip_run_id") != run:
            errors.append("opik_trace.paperclip_run_id mismatch")
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
    args = parser.parse_args()
    try:
        doc = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"BLOCKED: cannot read evidence: {exc}", file=sys.stderr)
        return 2
    problems = validate(doc)
    if problems:
        print(f"BLOCKED ({len(problems)} failed conditions):")
        for item in problems:
            print(f" - {item}")
        return 1
    print("PASS: all E2E DoD conditions are independently evidenced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
