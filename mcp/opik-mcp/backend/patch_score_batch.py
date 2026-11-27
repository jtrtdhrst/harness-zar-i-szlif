"""Apply an exact-source, fail-closed compatibility fix to the pinned MCP snapshot.

The Opik trace/span batch API accepts project_name/project_id on each score.
The installed 3.0.7.dev0 MCP was discarding both fields even when supplied.
Preserve only caller-supplied validated scope; do not infer it, change OAuth,
or touch single-target and thread wire routes.
"""
import ast
import hashlib
import pathlib
import sys
from typing import Any

SOURCE_SHA = "67e05d543038e15f65cdb5a59e8a55fe047992bcdbeb9910d2dca448f44eafc4"
OLD = '        item.pop("project_name", None)\n        item.pop("project_id", None)\n'
NEW = '        # Batch APIs require caller-supplied project scope for non-default projects.\n'
def patch(path: pathlib.Path) -> None:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise RuntimeError("unexpected_opik_observability_source_digest")
    source = raw.decode("utf-8")
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_score_batch_item")
    lines = source.splitlines(keepends=True)
    body = "".join(lines[fn.lineno-1:fn.end_lineno])
    if body.count(OLD) != 1:
        raise RuntimeError("unexpected_batch_scope_adapter")
    modified = "".join(lines[:fn.lineno-1]) + body.replace(OLD, NEW, 1) + "".join(lines[fn.end_lineno:])
    compile(modified, str(path), "exec")
    patched = ast.parse(modified)
    original_functions = {n.name: ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)}
    patched_functions = {n.name: ast.dump(n) for n in patched.body if isinstance(n, ast.FunctionDef)}
    assert original_functions.keys() == patched_functions.keys()
    assert all(original_functions[k] == patched_functions[k] for k in original_functions if k != "_score_batch_item")
    test_fn = next(n for n in patched.body if isinstance(n, ast.FunctionDef) and n.name == "_score_batch_item")
    ns = {"Any": Any}
    exec(compile(ast.Module(body=[test_fn], type_ignores=[]), str(path), "exec"), ns)
    adapt = ns["_score_batch_item"]
    uid = "0193a300-0000-7000-8000-000000000001"
    project = "0193a300-0000-7000-8000-000000000002"
    for target in ("trace", "span"):
        data = {"target": target, "target_id": uid, "project_name": "non-default", "project_id": project, "name": "score", "value": 0.5}
        out = adapt(dict(data), target)
        assert out == {"id": uid, "project_name": "non-default", "project_id": project, "name": "score", "value": 0.5}
        assert adapt({"target": target, "target_id": uid}, target) == {"id": uid}
        assert adapt({"target": target, "target_id": uid, "project_name": "non-default"}, target) == {"id": uid, "project_name": "non-default"}
        assert adapt({"target": target, "target_id": uid, "project_id": project}, target) == {"id": uid, "project_id": project}
    assert adapt({"target": "thread", "target_id": "thread-key", "project_id": project}, "thread") == {"thread_id": "thread-key", "project_id": project}
    path.write_text(modified, encoding="utf-8")
    print("OPIK_SCORE_BATCH_SCOPE_REGRESSION_PASS")

if __name__ == "__main__":
    patch(pathlib.Path(sys.argv[1]))
