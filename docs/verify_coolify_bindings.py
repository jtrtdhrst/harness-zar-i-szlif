#!/usr/bin/env python3
"""Fail-closed Coolify monorepo source-binding verification. Python stdlib only.

Structural check (no network):
 python3 docs/verify_coolify_bindings.py --repo-root . --manifest docs/coolify-source-bindings.json

Live-config check (requires sanitized Coolify readback):
 python3 docs/verify_coolify_bindings.py --repo-root . --manifest docs/coolify-source-bindings.json --observed docs/coolify-observed-20261101.json

The second mode MUST fail until each image-only Compose resource has an approved
Git-backed successor with source, webhook, full build and real MCP E2E evidence.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import sys

def inspect(manifest: dict, root: pathlib.Path, observed: dict | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    successes: list[str] = []
    items = manifest.get("git_build_candidates") or []
    if len(items) != 9:
        errors.append(f"Expected exactly nine audited MCP candidates, got {len(items)}")
    names: set[str] = set()
    targets: set[str] = set()
    for item in items:
        name = item["name"]
        repo = item["source"]["repository"]
        branch = item["source"]["branch"]
        base = item["source"]["base_directory"]
        dockerfile = item["source"]["dockerfile_location"]
        watch = item["source"]["watch_paths"]
        path = base.strip("/")
        if name in names or item["resource_uuid"] in targets:
            errors.append(f"{name}: duplicate resource or name")
        names.add(name)
        targets.add(item["resource_uuid"])
        if repo != manifest["policy"]["source_repo"] or branch != "main":
            errors.append(f"{name}: source repo/branch mismatch")
        if not path or path.startswith("_") or any(part in ("..", ".") for part in pathlib.PurePosixPath(path).parts):
            errors.append(f"{name}: invalid build context")
            continue
        if not dockerfile.startswith("/") or "/" in dockerfile[1:]:
            errors.append(f"{name}: Dockerfile must be inside build context")
            continue
        if watch != f"{path}/**":
            errors.append(f"{name}: cross-folder watch path forbidden")
        if not (root / path / dockerfile.lstrip("/")).is_file():
            errors.append(f"{name}: missing Dockerfile {path}/{dockerfile.lstrip('/')}")
        else:
            successes.append(f"{name}: source Dockerfile exists")
    if observed is not None:
        allowed = observed.get("github_app_can_read_harness") is True
        if not allowed:
            errors.append("Coolify GitHub App does NOT have harness private repository access")
        deployed = observed.get("git_backed_apps", {})
        for item in items:
            name = item["name"]
            d = deployed.get(name)
            if not d:
                errors.append(f"{name}: no Git-backed Coolify application found")
                continue
            src = item["source"]
            for k in ("repository", "branch", "base_directory", "dockerfile_location", "watch_paths"):
                if d.get(k) != src[k]:
                    errors.append(f"{name}: Coolify source field {k} does not match manifest")
            checks = d.get("e2e", {})
            for k in ("build", "health", "mcp_initialize", "mcp_tools_list", "authorized_tool_call", "unauthorized_denied", "same_sha", "webhook_triggered", "unrelated_path_ignored", "rollback_verified", "independent_review"):
                if checks.get(k) is not True:
                    errors.append(f"{name}: missing E2E proof {k}")
    return successes, errors

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--repo-root",type=pathlib.Path,default=pathlib.Path("."))
    p.add_argument("--manifest",type=pathlib.Path,required=True)
    p.add_argument("--observed",type=pathlib.Path)
    a=p.parse_args()
    try:
        m=json.loads(a.manifest.read_text())
        o=json.loads(a.observed.read_text()) if a.observed else None
    except (OSError,ValueError) as err:
        print(f"FAIL: cannot read evidence: {err}")
        return 2
    ok,bad=inspect(m,a.repo_root,o)
    print(f"SOURCE CHECKS: {len(ok)} passed")
    for x in bad:
        print(f"BLOCKED: {x}")
    if bad:
        print(f"RESULT: NOT READY ({len(bad)} conditions failed)")
        return 1
    if o is None:
        print("RESULT: SOURCE STRUCTURE PASS; live Coolify auto-deploy NOT tested")
    else:
        print("RESULT: live source+E2E evidence PASS")
    return 0

if __name__=="__main__":
    sys.exit(main())
