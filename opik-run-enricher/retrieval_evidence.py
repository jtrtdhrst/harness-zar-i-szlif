"""Safely summarize observed RepoWise and Hindsight calls in Paperclip pc_obs logs.

Only agent/run identifiers are used for matching. No raw arguments, memory
contents, source snippets or unsanitized tool results are exported.
"""
import hashlib
import json
import re

TOOLS = frozenset({
    "get_answer", "get_context", "get_symbol", "search_codebase",
    "get_risk", "get_change_risk", "get_why", "get_overview",
    "get_health", "get_dead_code", "list_repos",
    "get_architecture", "get_blast_radius", "get_dependency_path",
    "get_execution_flows", "get_conformance",
})
CODES = frozenset({
    "SUCCESS", "TIMEOUT", "RATE_LIMITED", "NOT_FOUND", "TOOL_NOT_FOUND",
    "UNAUTHORIZED", "AUTH_DENIED", "PERMISSION_DENIED",
    "NETWORK_ERROR", "VALIDATION_FAILED", "UNKNOWN_ERROR",
})

def summarize(raw: bytes, run: str, agent: str) -> dict:
    """Return evidence of observed retrieval, NOT a correctness verdict."""
    attempts = results = recalls = retains = 0
    categories = {}
    targets = set()
    for line in raw.splitlines():
        if b"pc_obs " not in line:
            continue
        try:
            outer = json.loads(line)
            chunk = outer.get("chunk")
            if not isinstance(chunk, str) or not chunk.startswith("pc_obs "):
                continue
            event = json.loads(chunk[7:])
            if event.get("paperclip_run_id") != run or event.get("paperclip_agent_id") != agent:
                continue
            kind = event.get("kind")
            if kind == "HINDSIGHT_RECALL":
                recalls += 1
                continue
            if kind == "HINDSIGHT_RETAIN":
                retains += 1
                continue
            if kind not in ("MCP_CALL_ATTEMPT", "MCP_CALL_RESULT"):
                continue
            server = event.get("mcp_server")
            tool = event.get("tool")
            if not isinstance(server, str) or not isinstance(tool, str):
                continue
            if not re.fullmatch(r"repowise(?:[-_.][a-z0-9]+)*", server.lower()):
                continue
            normalized = tool.removeprefix("mcp__Repowise__").rsplit(".", 1)[-1]
            if normalized not in TOOLS:
                continue
            parts = re.split(r"[-_.]", server.lower())
            targets.add("harness" if "harness" in parts else "product" if "product" in parts else "unknown")
            if kind == "MCP_CALL_ATTEMPT":
                attempts += 1
            else:
                results += 1
                code = event.get("error_code")
                label = code if isinstance(code, str) and code in CODES else "OTHER"
                categories[label] = categories.get(label, 0) + 1
        except (ValueError, TypeError, KeyError):
            continue
    return {
        "repowise_attempt_events": attempts,
        "repowise_result_events": results,
        "repowise_result_categories": categories,
        "repowise_server_target_hints": sorted(targets),
        "hindsight_recall_events": recalls,
        "hindsight_retain_events": retains,
        "observed_retrieval_events": attempts + results + recalls + retains,
        "source_log_sha256": hashlib.sha256(raw).hexdigest(),
        "correct_repo_sha_verified": False,
        "role_bank_verified": False,
        "functional_outcome_verified": False,
        "raw_payload_exported": False,
    }
