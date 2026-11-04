"""Apply the audited Paperclip run-grant bridge to pinned Hermes v0.22.5 at build time."""
from __future__ import annotations
import ast
import hashlib
from pathlib import Path

TARGET = Path("/opt/hermes/gateway/platforms/api_server_runs.py")
EXPECTED_SHA256 = "a9c3b02e51407ca30fc948753149984c0ec75dcc047763cf75a356c1baaba466"

def patch_source(original: str) -> str:
    code = original
    def once(old: str, new: str) -> None:
        nonlocal code
        n = code.count(old)
        if n != 1:
            raise RuntimeError(f"Pinned Hermes source drift: anchor count {n}")
        code = code.replace(old, new, 1)

    once("from contextlib import suppress\n", "from contextlib import nullcontext, suppress\n")

    once("    turn_author: Optional[dict[str, Any]] = None  # memory-attribution label only; grants nothing\n",
         "    turn_author: Optional[dict[str, Any]] = None  # memory-attribution label only; grants nothing\n"
         "    paperclip_run_mcp: Optional[dict[str, Any]] = None  # ephemeral only\n"
         "    paperclip_run_id: str = \"\"\n")

    once(
        "    try:\n        body = await request.json()\n    except Exception:\n        return _json_error(_openai_error, \"Invalid JSON\", status=400)\n    body, room_error = await self._normalize_room_dispatch(request, body)\n",
        "    try:\n        body = await request.json()\n    except Exception:\n        return _json_error(_openai_error, \"Invalid JSON\", status=400)\n"
        "    if not isinstance(body, dict):\n"
        "        return _json_error(_openai_error, \"Invalid JSON object\", status=400)\n"
        "    # Strip private credentials before any room, prompt, history or status processing.\n"
        "    paperclip_run_mcp_supplied = \"paperclip_run_mcp\" in body\n"
        "    paperclip_run_mcp = body.pop(\"paperclip_run_mcp\", None)\n"
        "    paperclip_run_id = request.headers.get(\"X-Paperclip-Run-Id\", \"\")\n"
        "    if paperclip_run_mcp_supplied:\n"
        "        from gateway.run_mcp import InvalidRunGrant, validate_grant\n"
        "        profile = _api_server._api_request_profile.get()\n"
        "        try:\n"
        "            if not profile or not paperclip_run_id or str(uuid.UUID(paperclip_run_id)) != paperclip_run_id:\n"
        "                raise InvalidRunGrant(\"invalid run MCP grant\")\n"
        "            # Bind run credentials to the exact session and idempotency identity.\n"
        "            if (request.headers.get(\"Idempotency-Key\") != paperclip_run_id\n"
        "                    or request.headers.get(\"X-Hermes-Session-Key\") != f\"paperclip:run:{paperclip_run_id}\"):\n"
        "                raise InvalidRunGrant(\"invalid run MCP routing\")\n"
        "            validate_grant(paperclip_run_mcp, authenticated_profile=str(profile), run_id=paperclip_run_id)\n"
        "        except (ValueError, TypeError, InvalidRunGrant):\n"
        "            return _json_error(_openai_error, \"Run MCP authorization rejected\", code=\"run_mcp_authorization_failed\", status=403)\n"
        "    body, room_error = await self._normalize_room_dispatch(request, body)\n")

    once(
        "    if room_error is not None:\n        return room_error\n    room_dispatch, room_execution_policy = (\n",
        "    if room_error is not None:\n        return room_error\n"
        "    if paperclip_run_mcp_supplied and (body.get(\"hosted_room_dispatch\") or body.get(\"_room_execution_policy\")):\n"
        "        return _json_error(_openai_error, \"Run MCP requires isolated API execution\", status=403)\n"
        "    room_dispatch, room_execution_policy = (\n")

    once(
        "    idempotency_scope, idempotency_fingerprint = _run_idempotency_identity(\n"
        "        self, request, body, gateway_session_key, idempotency_key)\n",
        "    idempotency_scope, idempotency_fingerprint = _run_idempotency_identity(\n"
        "        self, request, body, gateway_session_key, idempotency_key)\n"
        "    if paperclip_run_mcp_supplied and idempotency_key:\n"
        "        grant_digest = hashlib.sha256(json.dumps(paperclip_run_mcp, sort_keys=True).encode()).hexdigest()\n"
        "        idempotency_fingerprint = hashlib.sha256((idempotency_fingerprint + ':' + grant_digest).encode()).hexdigest()\n")

    once(
        "        turn_author=turn_author, walked_from=walked_from if session_id == stored_session_id else None)\n",
        "        turn_author=turn_author, walked_from=walked_from if session_id == stored_session_id else None,\n"
        "        paperclip_run_mcp=paperclip_run_mcp, paperclip_run_id=paperclip_run_id if paperclip_run_mcp_supplied else \"\")\n")

    once(
        "    admitted = await self._admit_to_live_bot_chat(session_id, user_message, turn_author) if selected_session_id else None\n",
        "    # A run-scoped grant must not silently move into a live Bot Chat without its MCP context.\n"
        "    admitted = (await self._admit_to_live_bot_chat(session_id, user_message, turn_author)\n"
        "                if selected_session_id and not paperclip_run_mcp_supplied else None)\n")

    once(
        "    effective_task_id = session_id or run.run_id\n",
        "    effective_task_id = (f\"paperclip:run:{run.paperclip_run_id}\" if run.paperclip_run_mcp is not None\n"
        "                         else (session_id or run.run_id))\n")

    once(
        "            r = agent.run_conversation(\n"
        "                user_message=run.user_message, conversation_history=run.conversation_history,\n"
        "                task_id=effective_task_id, **author_kwargs)\n",
        "            if run.paperclip_run_mcp is None:\n"
        "                grant_scope = nullcontext()\n"
        "            else:\n"
        "                from gateway.run_mcp import borrowed_run_tools\n"
        "                grant_scope = borrowed_run_tools(\n"
        "                    _api_server, run.paperclip_run_mcp,\n"
        "                    authenticated_profile=str(run.request_profile or \"\"), run_id=run.paperclip_run_id)\n"
        "            # Scoped MCP connections are torn down on success, error, and worker cancellation.\n"
        "            with grant_scope:\n"
        "                r = agent.run_conversation(\n"
        "                    user_message=run.user_message, conversation_history=run.conversation_history,\n"
        "                    task_id=effective_task_id, **author_kwargs)\n")

    ast.parse(code)
    return code

def main() -> None:
    original = TARGET.read_bytes()
    if hashlib.sha256(original).hexdigest() != EXPECTED_SHA256:
        raise SystemExit("Pinned Hermes source checksum mismatch; run MCP bridge not installed")
    result = patch_source(original.decode("utf-8"))
    TARGET.write_text(result, encoding="utf-8")
    print("Hermes run MCP receiver installed: pinned hash validated, private runtime only")

if __name__ == "__main__":
    main()
