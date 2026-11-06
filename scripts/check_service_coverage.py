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
                continue
            if re.match(r"    [\w-]+\s*:", part):
                in_paths = False
            if in_paths:
                patterns.extend(re.findall(r"[\"']([^\"']+)[\"']", part))
        return any(
            pattern == f"{root_name}/**"
            or pattern == f"{root_name}/**/*"
            or pattern.startswith(f"{root_name}/")
            for pattern in patterns
        )
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
        else:
            raise ValueError(f"{name}: unknown coverage mode {mode!r}")

    return len(roots), sum(e["mode"] == "workflow" for e in entries.values())


if __name__ == "__main__":
    roots, covered = check()
    print(f"PASS: {roots} root folders explicitly classified; {covered} have targeted workflow path coverage")
