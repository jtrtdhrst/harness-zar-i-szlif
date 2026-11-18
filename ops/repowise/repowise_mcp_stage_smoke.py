#!/usr/bin/env python3
# Stage-only MCP smoke; never prints the API key or tool payloads.
import json
import os
import urllib.error
import urllib.request

URL = os.environ.get("REPOWISE_MCP_URL", "http://127.0.0.1:7338/mcp")
KEY = os.environ.get("REPOWISE_API_KEY", "")
PROTOCOL = "2025-06-18"
session_id = None
next_id = 1


def fail(message):
    raise SystemExit(f"FAIL {message}")


def rpc(method, params=None):
    global session_id, next_id
    request_id = next_id
    next_id += 1
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "user-agent": "repowise-stage-smoke/1.0",
    }
    if KEY:
        headers["authorization"] = f"Bearer {KEY}"
    if session_id:
        headers["mcp-session-id"] = session_id
        headers["mcp-protocol-version"] = PROTOCOL
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode()
            session_id = response.headers.get("mcp-session-id", session_id)
            content_type = response.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        fail(f"{method} HTTP {exc.code}")
    except Exception as exc:
        fail(f"{method} transport {type(exc).__name__}")
    if "text/event-stream" in content_type:
        messages = [line[6:] for line in raw.splitlines() if line.startswith("data: ")]
        if not messages:
            fail(f"{method} returned empty event stream")
        raw = messages[-1]
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        fail(f"{method} returned invalid JSON")
    if "error" in result:
        fail(f"{method} JSON-RPC {result['error'].get('code')}")
    if result.get("id") != request_id:
        fail(f"{method} response id mismatch")
    return result.get("result")


def tool(name, arguments=None):
    result = rpc("tools/call", {"name": name, "arguments": arguments or {}})
    if not isinstance(result, dict) or result.get("isError"):
        fail(f"tool {name} failed")
    parts = [item.get("text", "") for item in result.get("content", []) if item.get("type") == "text"]
    text = "\n".join(parts)
    try:
        return json.loads(text), text
    except json.JSONDecodeError:
        return text, text


def main():
    if not KEY:
        fail("REPOWISE_API_KEY is not set")
    rpc("initialize", {
        "protocolVersion": PROTOCOL,
        "capabilities": {},
        "clientInfo": {"name": "repowise-stage-smoke", "version": "1"},
    })
    tools = rpc("tools/list", {})
    names = {item.get("name") for item in tools.get("tools", [])}
    required = {"list_repos", "search_codebase", "get_context", "get_blast_radius"}
    if not required <= names:
        fail("tools/list missing required tools")
    print("PASS initialize/tools-list")

    repos, repos_text = tool("list_repos")
    if not isinstance(repos, dict) or "repos" not in repos:
        fail("list_repos did not return structured JSON")
    aliases = {item.get("alias") for item in repos.get("repos", [])}
    if aliases != {"product", "harness"}:
        fail("list_repos aliases differ")
    print("PASS both repository aliases")

    checks = [
        ("product", "app/mcp-worker/src/index.ts"),
        ("harness", "scripts/service-coverage.json"),
    ]
    for alias, target in checks:
        search, raw = tool("search_codebase", {"query": target, "repo": alias, "mode": "path", "limit": 3})
        found = any(item.get("path") == target for item in search.get("results", [])) if isinstance(search, dict) else target in raw
        if not found:
            fail(f"search_codebase missed {alias} target")
        context, context_text = tool("get_context", {"targets": [target], "repo": alias, "include": ["skeleton"]})
        if target not in context_text:
            fail(f"get_context missed {alias} target")
        print(f"PASS {alias} search/context")

    wrong_repo_search, _ = tool("search_codebase", {"query": "scripts/product_native_promotion.py", "repo": "product", "mode": "path", "limit": 5})
    if any(item.get("path") == "scripts/product_native_promotion.py" for item in wrong_repo_search.get("results", [])):
        fail("repo contamination: harness-only file surfaced as product")
    print("PASS negative cross-repo ownership check")

    blast, blast_text = tool("get_blast_radius", {"targets": ["product::app"], "max_depth": 2, "include_behavioral": False})
    # Paperclip MCP was removed from Harness on 2026-11-18. Verify a
    # surviving cross-repository HTTP relationship instead of deleted code.
    if not isinstance(blast, dict):
        fail("cross-repo blast radius is not structured JSON")
    if blast.get("unresolved_targets") or blast.get("undetermined_targets"):
        fail("cross-repo blast radius has unresolved targets")
    impacted = blast.get("impacted", [])
    if not isinstance(impacted, list):
        fail("cross-repo blast radius has invalid impacted list")
    ubuntu_edges = [
        item for item in impacted
        if isinstance(item, dict)
        and item.get("id") == "harness::ubuntu-mcp"
        and item.get("repo") == "harness"
        and item.get("structural") is True
        and "http" in item.get("edge_kinds", [])
    ]
    if not ubuntu_edges:
        fail("cross-repo blast radius missing structural HTTP edge to harness::ubuntu-mcp")
    print("PASS cross-repo blast radius (ubuntu-mcp structural HTTP)")
    print("ALL PASS")


if __name__ == "__main__":
    main()
