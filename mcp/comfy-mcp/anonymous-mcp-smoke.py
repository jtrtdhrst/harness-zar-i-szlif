#!/usr/bin/env python3
"""Anonymous ComfyUI MCP public endpoint end-to-end smoke test (stdlib only)."""
import hashlib
import json
import os
import urllib.request

URL = os.environ.get("MCP_URL", "https://mcp-comfy.kompaszbiorek.pl/mcp")
KNOWN_PROMPT = os.environ.get("COMFY_MCP_SMOKE_PROMPT_ID", "afad26b4-6600-4788-bbd2-dd3fbe739d28")
STAGE = os.environ.get("MCP_E2E_STAGE") == "1"
session = None


def rpc(method, request_id=None, params=None):
    message = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        message["id"] = request_id
    if params is not None:
        message["params"] = params
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if session:
        headers["Mcp-Session-Id"] = session
    req = urllib.request.Request(
        URL, data=json.dumps(message).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        body = response.read().decode()
        if request_id is None:
            assert response.status in (200, 202, 204), response.status
            return None, response.headers
        assert response.status == 200, response.status
        data = next((line[6:] for line in body.splitlines() if line.startswith("data: ")), body)
        result = json.loads(data)
        assert "error" not in result, result.get("error")
        assert not result.get("result", {}).get("isError"), result.get("result")
        return result["result"], response.headers


def call(name, args, request_id):
    return rpc("tools/call", request_id, {"name": name, "arguments": args})[0]


def text_result(result):
    return next(c["text"] for c in result["content"] if c["type"] == "text")


def main():
    global session
    result, headers = rpc(
        "initialize", 1, {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "anonymous-e2e-smoke", "version": "1"},
        }
    )
    assert result["serverInfo"]["name"] == "comfyui-mcp", result["serverInfo"]
    session = headers["Mcp-Session-Id"]
    assert session
    rpc("notifications/initialized")
    tools, _ = rpc("tools/list", 2, {})
    names = {t["name"] for t in tools["tools"]}
    for required in ("get_system_stats", "get_output_image_ref", "stage_output_image_reference", "upload_chatgpt_image"):
        assert required in names, required
    health = text_result(call("get_system_stats", {"action": "health"}, 3))
    assert "**ComfyUI**:" in health, health[:300]
    result = text_result(call("get_output_image_ref", {"prompt_id": KNOWN_PROMPT}, 4))
    image = json.loads(result[result.index("{"):])["primary"]
    with urllib.request.urlopen(image["view_url"], timeout=30) as response:
        assert response.status == 200
        raw = response.read()
    assert len(raw) == image["bytes"]
    assert hashlib.sha256(raw).hexdigest() == image["sha256"]
    print("PASS anonymous initialize / tools/list / get_system_stats")
    print("PASS image view HTTP 200 / original bytes / SHA-256")
    print("tools_count=", len(names), "image_id=", image["image_id"])
    if STAGE:
        stage = text_result(call("stage_output_image_reference", {"image_id": image["image_id"]}, 5))
        staged = json.loads(stage[stage.index("{"):])
        assert staged["byte_identical"] and staged["loader_selectable"], staged
        assert staged["sha256"] == image["sha256"]
        print("PASS stage_output_image_reference / LoadImage / SHA-256")
    else:
        print("SKIP stage write (set MCP_E2E_STAGE=1 to test)")


if __name__ == "__main__":
    main()
