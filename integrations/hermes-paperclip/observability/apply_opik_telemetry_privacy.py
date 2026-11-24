#!/usr/bin/env python3
"""Source-pinned metadata-only observability overlay for the Hermes Opik plugin.

Apply on staged copies AFTER the existing PR #39 role-segmentation transform.
This never edits the running Gateway and must not run without review.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

BASE_HOOKS_SHA256 = "8fb15f3f78fa8c078748f7ec39b4d1242e63a11e5c38048d726e97d690151a0a"
SEGMENTED_LIFECYCLE_SHA256 = "d25ba46c79f80e9d8c34157b73636bb2ddebdfdf46f0fe74679db24141c8ffec"

def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("source anchor drift; refusing telemetry patch")
    return text.replace(old,new,1)

HELPERS = '''
# Privacy boundary: everything below is computed from event categories and
# scalar presence/counts, never from prompts, tool arguments or memory values.
def _safe_tool_label(value: Any) -> str:
    if not isinstance(value, str):
        return "unknown_tool"
    if value in {"hindsight_recall", "hindsight_retain"}:
        return value
    if value.startswith("mcp__"):
        return "mcp_tool"
    if value.startswith(("wiki_", "skills_")):
        return "knowledge_tool"
    if value in {"tool_search", "tool_describe", "read_file", "execute_code"}:
        return value
    return "other_tool"


def _reported_tool_outcome(value: Any) -> str:
    # Only machine-readable boolean flags can establish an outcome. No content
    # parsing; tool errors embedded in strings cannot safely be classified.
    if isinstance(value, dict):
        if value.get("isError") is True or value.get("success") is False:
            return "reported_error"
        if value.get("isError") is False or value.get("success") is True:
            return "reported_no_error"
    return "unverified"


def _configured_bank_for_tool(value: Any) -> dict[str, Any]:
    if value not in ("hindsight_recall", "hindsight_retain"):
        return {}
    source_file = str(Path(__file__).with_name("lifecycle.py"))
    role = _verified_role_from_plugin_path(source_file)
    if not role:
        return {}
    mode = _configured_hindsight_mode(source_file, role)
    if not mode:
        return {}
    return {"configured_memory_bank": "hermes-" + role,
            "configured_memory_backend": mode,
            "memory_bank_provenance": "profile_config_only_not_call_proof"}

'''

def transform_hooks(original: str) -> str:
    text = original
    text = replace_once(text, "import datetime\n", "import datetime\nimport hashlib\nfrom pathlib import Path\n")
    text = replace_once(
        text, "from .lifecycle import finish_trace, flush_trace_create, start_root_trace\n",
        "from .lifecycle import (finish_trace, flush_trace_create, start_root_trace,\n"
        "    _verified_role_from_plugin_path, _configured_hindsight_mode)\n")
    text = replace_once(text, "\ndef on_pre_llm_call(\n", "\n"+HELPERS+"def on_pre_llm_call(\n")
    text = replace_once(text, 'input={"messages": serialize_messages(input_messages)},',
       'input={"message_count": len(input_messages) if isinstance(input_messages, (tuple, list)) else 0,\n'
       '                   "content_redacted": True},')
    text = replace_once(text, 'metadata={"platform": platform, "api_mode": api_mode, "base_url": base_url},',
       'metadata={"platform": platform, "api_mode": api_mode, "raw_payload_exported": False},')
    text = replace_once(text, 'finish_trace(task_key, output={"content": safe_value(assistant_response)})',
       'finish_trace(task_key, output={"content_present": bool(assistant_response), "content_redacted": True})')

    before = '''    if assistant_message is not None:
        output = serialize_assistant_message(assistant_message)
        tool_calls = serialize_tool_calls(
            getattr(assistant_message, "tool_calls", None)
        )
    elif assistant_response is not None:
        output = assistant_output(content=safe_value(assistant_response))
        tool_calls = []
    else:
        tool_calls = (
            [{"id": f"tc_{i}"} for i in range(assistant_tool_call_count)]
            if assistant_tool_call_count
            else []
        )
        output = assistant_output(
            content=f"[{assistant_content_chars} chars]"
            if assistant_content_chars
            else None,
            tool_calls=tool_calls,
        )
'''
    after = '''    # No text, reasoning, provider function arguments or generated tool calls
    # leave Hermes. Tool operation counts and LLM usage remain observable.
    tool_calls = []
    reported_calls = getattr(assistant_message, "tool_calls", None) if assistant_message is not None else None
    call_count = len(reported_calls) if isinstance(reported_calls, (list, tuple)) else 0
    output = {
        "content_redacted": True,
        "assistant_present": bool(assistant_message is not None or assistant_response is not None),
        "tool_call_count": min(10000, max(call_count, assistant_tool_call_count or 0)),
    }
'''
    text = replace_once(text,before,after)
    text = replace_once(text, 'tool_count = len(output.get("tool_calls", [])) or assistant_tool_call_count',
       'tool_count = output["tool_call_count"]')
    text = replace_once(text, 'gen_metadata["tool_call_count"] = tool_count',
       'gen_metadata["tool_call_count"] = tool_count\n'
       '    gen_metadata["cost_status"] = "provider_estimate_unverified" if total_cost is not None else "unknown"')
    text = replace_once(text, 'gen_metadata["finish_reason"] = finish_reason',
       'gen_metadata["finish_reason"] = finish_reason if finish_reason in {"stop", "length", "tool_calls", "content_filter", "end_turn"} else "other"')
    text = replace_once(text, 'input=as_input_dict(safe_value(args)),',
       'input={"arguments_present": args is not None, "content_redacted": True},')
    before = '''    if isinstance(result, str):
        result_value = maybe_parse_json_string(result)
    else:
        result_value = result
    result_value = normalize_payload(result_value, tool_name=tool_name, args=args)
    safe_result_value = safe_value(result_value, parse_json_strings=True)
'''
    after = '''    # A tool may return credentials, arbitrary memory, or nested private data.
    # Only preserve bounded typed metadata; never inspect text for errors.
    outcome = _reported_tool_outcome(result)
    safe_result_value = {"result_present": result is not None,
                         "content_redacted": True, "outcome": outcome}
'''
    text = replace_once(text,before,after)
    text = replace_once(text,'span_input = pending.input if pending else as_input_dict(safe_value(args))',
       'span_input = pending.input if pending else {"arguments_present": args is not None, "content_redacted": True}')
    text = replace_once(text,'name=f"Tool: {tool_name}",','name=f"Tool: {_safe_tool_label(tool_name)}",')
    before='''            metadata={
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "args": safe_value(args, parse_json_strings=True),
            },
'''
    after='''            metadata={
                "tool_name": _safe_tool_label(tool_name),
                "tool_call_id_sha256": hashlib.sha256(str(tool_call_id).encode()).hexdigest()[:16] if tool_call_id else None,
                "outcome": outcome,
                "raw_payload_exported": False,
                **_configured_bank_for_tool(tool_name),
            },
'''
    text=replace_once(text,before,after)
    text=replace_once(text,
        '            },\n        )\n\n\ndef on_api_request_error(',
        '            },\n        )\n'
        '        state.turn_tool_calls.append({"tool_category": _safe_tool_label(tool_name), "outcome": outcome})\n\n\ndef on_api_request_error(')
    text=replace_once(text,'message = str(err.get("message") or reason or "API request error")',
       'message = "LLM request error (details redacted)"')
    text=replace_once(text,'exc_type = str(err.get("type") or "APIRequestError")',
       'exc_type = "APIRequestError"')
    text=replace_once(text,'            "reason": reason,\n','')
    text=replace_once(text,'                error_meta[k] = v',
       '                if (k == "retryable" and isinstance(v, bool)) or (k != "retryable" and type(v) is int and 0 <= v <= 99999):\n'
       '                    error_meta[k] = v')
    text=replace_once(text,'name=f"Subagent: {child_role or \'subagent\'}",',
       'name="Subagent: bounded",')
    text=replace_once(text,'input={"role": safe_value(child_role)} if child_role else {},',
       'input={"role_present": bool(child_role), "content_redacted": True},')
    text=replace_once(text,'output={"summary": safe_value(child_summary)} if child_summary else None,',
       'output={"summary_present": bool(child_summary), "content_redacted": True},')
    before='''                "child_role": child_role,
                "child_status": child_status,
                "duration_ms": duration_ms,
                "parent_session_id": parent,
'''
    after='''                "child_role": child_role if isinstance(child_role,str) and child_role in _KNOWN_OPIK_ROLES else "unverified",
                "child_status": child_status if child_status in {"completed", "failed", "cancelled", "timed_out"} else "unknown",
                "duration_ms": duration_ms if isinstance(duration_ms,(int,float)) and 0 <= duration_ms <= 86400000 else None,
                "parent_session_present": bool(parent),
                "raw_payload_exported": False,
'''
    text=replace_once(text,before,after)
    text=replace_once(text, '_verified_role_from_plugin_path, _configured_hindsight_mode)',
                      '_verified_role_from_plugin_path, _configured_hindsight_mode, _KNOWN_OPIK_ROLES)')
    ast.parse(text)
    return text

def transform_segmented_lifecycle(original: str) -> str:
    text=replace_once(original,'trace_input = extract_last_user_message(messages)',
       'trace_input = {"message_count": len(messages) if isinstance(messages,(tuple,list)) else 0,\n'
       '                   "content_redacted": True}')
    text=replace_once(text, '"name": trace_name_from_messages(messages) or "Hermes turn",',
       '"name": "Hermes turn",')
    text=replace_once(text, '        "task_id": task_id,',
       '        "task_id": _paperclip_thread_id(task_id, "") or None,')
    text=replace_once(text, '        "turn_id": turn_id,',
       '        "turn_id_present": bool(turn_id),')
    text=replace_once(text, '        "api_request_id": api_request_id,',
       '        "api_request_id_present": bool(api_request_id),')
    text=replace_once(text, '        "source": "hermes",',
       '        "source": "hermes",\n        "telemetry_privacy": "metadata_only_v1",')
    text=replace_once(text, '    # Build the create payload once and keep it:',
       '    if metadata["task_id"]:\n'
       '        metadata["paperclip_run_id"] = metadata["task_id"][len("paperclip:run:"):]\n'
       '        metadata["paperclip_run_id_provenance"] = "canonical_task_id_format_only"\n'
       '    # Build the create payload once and keep it:')
    start='def merge_trace_output(output: Any, state: TraceState) -> Any:\n'
    end='\ndef finish_trace(task_key: str, *, output: Any = None) -> None:\n'
    if text.count(start)!=1 or text.count(end)!=1:
        raise ValueError("source anchor drift in root finalization")
    i=text.index(start);j=text.index(end)
    text=text[:i]+'''def merge_trace_output(output: Any, state: TraceState) -> Any:
    """Never export the assistant message or tool results from root traces."""
    return {"content_redacted": True, "output_present": output is not None,
            "tool_call_count": len(state.turn_tool_calls), "raw_payload_exported": False}

'''+text[j:]
    ast.parse(text)
    return text

def prepare(lifecycle_file: Path, hooks_file: Path) -> tuple[str, str]:
    for p in (lifecycle_file,hooks_file):
        if p.is_symlink() or not p.is_file():
            raise ValueError("unsafe plugin source path")
    lifecycle=lifecycle_file.read_bytes()
    hooks=hooks_file.read_bytes()
    if hashlib.sha256(lifecycle).hexdigest()!=SEGMENTED_LIFECYCLE_SHA256:
        raise ValueError("segmented lifecycle SHA mismatch; no changes applied")
    if hashlib.sha256(hooks).hexdigest()!=BASE_HOOKS_SHA256:
        raise ValueError("pristine hooks SHA mismatch; no changes applied")
    return transform_segmented_lifecycle(lifecycle.decode()),transform_hooks(hooks.decode())

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("lifecycle_file",type=Path)
    p.add_argument("hooks_file",type=Path)
    p.add_argument("--check",action="store_true")
    args=p.parse_args()
    lifecycle,hooks=prepare(args.lifecycle_file,args.hooks_file)
    if not args.check:
        raise SystemExit("direct file writes disabled; use audited privacy_rollout.py")
    print("privacy overlay valid: metadata-only, source pinned (read-only)")

if __name__=="__main__":
    main()
