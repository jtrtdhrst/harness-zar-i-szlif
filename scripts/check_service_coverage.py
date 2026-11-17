#!/usr/bin/env python3
"""Fail closed when a repository root lacks an explicit CI/manual-only disposition."""
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "scripts/service-coverage.json"


def workflow_paths(path):
    text = path.read_text(encoding="utf-8")
    patterns = []
    for match in re.finditer(r"\bpaths:\s*(?:\[([^\]]*)\]|\n((?:\s+-[^\n]*\n?)+))", text):
        block = match.group(1) or match.group(2) or ""
        patterns.extend(re.findall(r"[\"']([^\"']+)[\"']", block))
    return patterns


def workflow_covers_root(path, root_name):
    """A CI job must run on every relevant PR update for this root.

    A path-unfiltered pull_request event covers every root. If filtered, only
    pull_request.paths counts; a push path filter must not mask a PR gap.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line != "  pull_request:":
            continue
        block = []
        for nested in lines[index + 1:]:
            if nested.strip() and not nested.startswith("    ") and not nested.lstrip().startswith("#"):
                break
            block.append(nested)
        substantive = [part for part in block if part.strip() and not part.lstrip().startswith("#")]
        if not substantive:
            return True
        if any(re.match(r"\s*paths-ignore\s*:", part) for part in substantive):
            return False
        # Only paths from this pull_request event, never from push or dispatch.
        patterns = []
        in_paths = False
        for part in substantive:
            if re.match(r"    paths\s*:", part):
                in_paths = True
                # Also handle YAML inline lists: paths: ['svc/**', 'other/**'].
                patterns.extend(re.findall(r"[\"']([^\"']+)[\"']", part))
                continue
            if re.match(r"    [\w-]+\s*:", part):
                in_paths = False
            if in_paths:
                patterns.extend(re.findall(r"[\"']([^\"']+)[\"']", part))
        return any(
            pattern in {f"{root_name}/**", f"{root_name}/**/*"}
            for pattern in patterns
        )
    return False



def workflow_has_required_test_step(path, required):
    """Check the exact unguarded command in the named CI job (not a comment)."""
    if not isinstance(required, dict) or not all(
        isinstance(required.get(k), str) and required[k].strip()
        for k in ("job", "name", "working_directory", "run")
    ):
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    job_marker = f"  {required['job']}:"
    if job_marker not in lines:
        return False
    start = lines.index(job_marker) + 1
    job_lines = []
    for line in lines[start:]:
        if re.match(r"^  [A-Za-z][\\w-]*:\\s*$", line):
            break
        job_lines.append(line)
    if any(re.match(r"^    (?:if|continue-on-error):", line) for line in job_lines):
        return False
    step_marker = f"      - name: {required['name']}"
    for index, line in enumerate(job_lines):
        if line != step_marker:
            continue
        step_lines = []
        for step_line in job_lines[index + 1:]:
            if step_line.startswith("      - "):
                break
            if step_line and not step_line.startswith("        ") and not step_line.lstrip().startswith("#"):
                break
            step_lines.append(step_line)
        if any(re.match(r"^        (?:if|continue-on-error):", s) for s in step_lines):
            continue
        if (
            f"        working-directory: {required['working_directory']}" in step_lines
            and f"        run: {required['run']}" in step_lines
        ):
            return True
    return False

def check(root=ROOT, config_path=CONFIG):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1 or not isinstance(config.get("entries"), dict):
        raise ValueError("invalid service coverage schema")

    roots = {p.name for p in root.iterdir() if p.is_dir() and p.name != ".git"}
    entries = config["entries"]
    missing, stale = roots - entries.keys(), entries.keys() - roots
    if missing or stale:
        raise ValueError(f"root coverage mismatch: missing={sorted(missing)}, stale={sorted(stale)}")

    for name, entry in entries.items():
        mode = entry.get("mode")
        if mode == "manual_only":
            if not entry.get("reason", "").strip():
                raise ValueError(f"{name}: manual_only requires a reason")
        elif mode == "workflow":
            workflows = entry.get("workflows")
            if not isinstance(workflows, list) or not workflows:
                raise ValueError(f"{name}: workflow disposition requires workflows")
            for workflow in workflows:
                path = root / workflow
                if not path.is_file():
                    raise ValueError(f"{name}: missing workflow {workflow}")
                if not workflow_covers_root(path, name):
                    raise ValueError(f"{name}: {workflow} does not path-filter this root or cover all pull requests")
                if entry.get("required_test_step") is not None and not workflow_has_required_test_step(path, entry["required_test_step"]):
                    raise ValueError(f"{name}: {workflow} missing mandatory unconditional test step")
        else:
            raise ValueError(f"{name}: unknown coverage mode {mode!r}")

    return len(roots), sum(e["mode"] == "workflow" for e in entries.values())


if __name__ == "__main__":
    roots, covered = check()
    print(f"PASS: {roots} root folders explicitly classified; {covered} have targeted workflow path coverage")
