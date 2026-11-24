"""Bounded, read-only execution diagnostics for agents; no raw payload output."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from uuid import UUID

METRICS = (
    "multica_run_completed", "multica_issue_dod_accepted",
    "multica_usage_measured", "multica_tool_flow_measured",
    "multica_queue_wait_seconds", "multica_dispatch_to_start_seconds",
    "multica_run_elapsed_seconds", "multica_first_observed_tool_call_seconds",
    "multica_attempt", "multica_input_tokens", "multica_output_tokens",
    "multica_cache_read_tokens", "multica_cache_write_tokens",
    "multica_tool_calls_observed", "multica_tool_pairing_ratio",
    "multica_repeated_tool_name_calls", "multica_first_valid_action_seconds",
    "multica_admission_failure_detected", "multica_session_reconcile_required",
    "multica_cancelled_after_tool_activity",
) + tuple(
    f"multica_{service}_{key}"
    for service in ("repowise", "hindsight")
    for key in ("calls", "retrieval", "analysis", "discovery", "write", "other",
                "paired", "truncated_results", "paired_duration_ms")
)
TOOL = re.compile(r"mcp__editor_(repowise|hindsight)_[a-z0-9_]{1,100}_[0-9a-f]{8}__[a-z0-9_]{1,64}")

def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None

def summary(record, project_id, trace_id):
    trace = record.get("trace")
    if not isinstance(trace, dict) or trace.get("id") != trace_id or trace.get("project_id") != project_id:
        raise ValueError("trace or project identity mismatch")
    spans = record.get("spans")
    if not isinstance(spans, list):
        spans = []
        span_coverage = "unavailable"
    elif record.get("spansTruncated") is True:
        span_coverage = "truncated"
    elif not spans:
        span_coverage = "no_inline_spans"
    else:
        span_coverage = "inline_spans"
    counts = Counter()
    for span in spans:
        if not isinstance(span, dict):
            continue
        if span.get("type") == "llm":
            counts["llm_spans"] += 1
        elif span.get("type") == "tool":
            counts["tool_spans"] += 1
            meta = span.get("metadata")
            name = meta.get("name") if isinstance(meta, dict) else None
            match = TOOL.fullmatch(name) if isinstance(name, str) else None
            if match:
                counts[match.group(1) + "_tool_spans"] += 1
    scores = {}
    for score in trace.get("feedback_scores") or []:
        if isinstance(score, dict) and score.get("name") in METRICS:
            v = number(score.get("value"))
            if v is not None:
                scores[score["name"]] = v
    usage = trace.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    meta = trace.get("metadata")
    meta = meta if isinstance(meta, dict) else {}
    native = meta.get("usage_token_counts")
    native = native if isinstance(native, list) else []
    token_keys = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
    tokens = {}
    for key in token_keys:
        vals = [number(e.get(key)) if isinstance(e, dict) else None for e in native]
        tokens[key] = sum(vals) if vals and all(v is not None for v in vals) else None
    # SDK token usage may exclude cache; never silently combine these accounting systems.
    sdk = {key: number(usage.get(key)) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    outcome = trace.get("output")
    status = outcome.get("status") if isinstance(outcome, dict) else None
    if status not in ("completed", "failed", "cancelled", "running", "queued", "dispatched"):
        status = None
    missing = []
    if "multica_issue_dod_accepted" not in scores:
        missing.append("accepted_dod")
    if not native or any(v is None for v in tokens.values()):
        missing.append("native_token_breakdown")
    if span_coverage != "inline_spans":
        missing.append("complete_inline_spans")
    if "multica_tool_flow_measured" not in scores:
        missing.append("native_tool_flow")
    if not any(k.startswith("multica_repowise_") for k in scores):
        missing.append("native_repowise_metrics")
    if not any(k.startswith("multica_hindsight_") for k in scores):
        missing.append("native_hindsight_metrics")
    return {
        "trace_id": trace_id, "project_id": project_id, "status": status,
        "duration_ms": number(trace.get("duration")), "span_coverage": span_coverage,
        "inline_span_counts": {k: counts[k] for k in ("llm_spans", "tool_spans", "repowise_tool_spans", "hindsight_tool_spans")},
        "native_tokens": tokens, "sdk_usage": sdk, "scores": scores,
        "missing_evidence": missing,
        "limits": "Only this trace; no session join. Tool spans and paired results do not prove success, relevance or accepted DoD. Missing values are unknown."
    }

async def execution_summary(project_id: str, trace_id: str) -> str:
    """Compact execution facts for one Opik trace, including cache, retrieval, coverage and outcome gaps. No raw prompts, memory, tool arguments or outputs. Missing evidence is unknown; does not join separate runtime traces."""
    from opik_mcp.read_list.read_tool import run_read
    from mcp.server.fastmcp.exceptions import ToolError
    try:
        project_id, trace_id = str(UUID(project_id)), str(UUID(trace_id))
    except (ValueError, TypeError) as exc:
        raise ToolError("project_id and trace_id must be UUIDs") from exc
    # Use the existing authorized read path, no new credential or data source.
    raw = await run_read(entity_type="trace", id=trace_id)
    try:
        record = json.loads(raw[raw.index("\n{") + 1:])
        return json.dumps(summary(record, project_id, trace_id), separators=(",", ":"))
    except (ValueError, TypeError, KeyError) as exc:
        raise ToolError("execution summary unavailable or trace/project identity mismatch") from exc

def register(mcp):
    from opik_mcp.server.tools.hints import READS
    mcp.tool(title="Summarize execution evidence", annotations=READS, structured_output=False)(execution_summary)

def self_test():
    t = "00000000-0000-0000-0000-000000000001"
    p = "00000000-0000-0000-0000-000000000002"
    record = {"trace": {"id": t, "project_id": p, "output": {"status": "completed", "secret": "PRIVATE"},
                        "metadata": {"usage_token_counts": [{"input_tokens": 2, "output_tokens": 3, "cache_read_tokens": 100, "cache_write_tokens": 0}]},
                        "feedback_scores": [{"name": "multica_run_completed", "value": 1}, {"name": "SECRET_SCORE", "value": 1}]},
              "spans": [{"type": "tool", "metadata": {"name": "mcp__editor_repowise_harness_1234abcd__search_codebase"}, "input": "PRIVATE"},
                        {"type": "tool", "metadata": {"name": "mcp__editor_hindsight_coo_1234abcd__recall"}},
                        {"type": "llm"}], "spansTruncated": True}
    s = summary(record, p, t)
    assert s["inline_span_counts"] == {"llm_spans": 1, "tool_spans": 2, "repowise_tool_spans": 1, "hindsight_tool_spans": 1}
    assert s["native_tokens"]["cache_read_tokens"] == 100
    assert "accepted_dod" in s["missing_evidence"] and s["span_coverage"] == "truncated"
    assert "PRIVATE" not in str(s) and "SECRET_SCORE" not in str(s)
    try:
        summary(record, t, t)
    except ValueError:
        pass
    else:
        raise AssertionError("cross-project mismatch not rejected")
    assert summary({"trace":{"id":t,"project_id":p}},p,t)["native_tokens"]["cache_read_tokens"] is None
    print("EXECUTION_SUMMARY_REGRESSION_PASS")

if __name__ == "__main__":
    self_test()
