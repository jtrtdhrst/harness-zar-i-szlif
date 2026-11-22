#!/usr/bin/env python3
"""Select only four source-ready Harness runtime images not owned by MCP OCI lane.

Publication of a digest is never authorization to deploy or clear HOLD.
"""
import json
import os
from pathlib import Path
import subprocess

REPOSITORY = "jtrtdhrst/harness-zar-i-szlif"
SERVICE_ROOTS = {
    "github-ops-mcp": ("github-mcp", "github-mcp/Dockerfile"),
    "hermes-gateway": ("integrations/hermes-paperclip/gateway",
                       "integrations/hermes-paperclip/gateway/Dockerfile"),
    "multica-mcp": ("multica-mcp", "multica-mcp/Dockerfile"),
    "repowise-deployment-publisher-staging": (
        "ops/repowise", "ops/repowise/Dockerfile.publisher"),
}
CONTROL_PATHS = {
    "scripts/select_owned_runtime_builds.py",
    ".github/workflows/owned-runtime-images-ghcr.yml",
    "ops/service-build-roots.json",
}

def select(paths, *, event_name, service="all"):
    if event_name == "workflow_dispatch":
        if service == "all":
            selected = set(SERVICE_ROOTS)
        elif service in SERVICE_ROOTS:
            selected = {service}
        else:
            raise ValueError("invalid_owned_runtime_service")
    elif event_name == "push":
        paths = set(paths)
        selected = (set(SERVICE_ROOTS) if CONTROL_PATHS & paths else {
            name for name, (root, _) in SERVICE_ROOTS.items()
            if any(p.startswith(root + "/") for p in paths)
        })
    else:
        raise ValueError("untrusted_event")
    return [
        {"service": name, "directory": SERVICE_ROOTS[name][0],
         "dockerfile": SERVICE_ROOTS[name][1]}
        for name in sorted(selected)
    ]

def main():
    if (os.environ.get("GITHUB_REPOSITORY") != REPOSITORY or
            os.environ.get("GITHUB_REF") != "refs/heads/main"):
        raise SystemExit("untrusted_repository_or_ref")
    sha = os.environ["GITHUB_SHA"]
    if len(sha) != 40 or any(x not in "0123456789abcdef" for x in sha):
        raise SystemExit("invalid_source_sha")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if actual != sha:
        raise SystemExit("source_sha_mismatch")
    event_name = os.environ["GITHUB_EVENT_NAME"]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    if event_name == "push":
        before = event.get("before", "")
        if before and before != "0" * 40:
            changed = subprocess.check_output(
                ["git", "diff", "--name-only", "--no-renames", before, sha],
                text=True).splitlines()
        else:
            changed = list(CONTROL_PATHS)
    else:
        changed = []
    selected = select(changed, event_name=event_name,
                      service=os.environ.get("INPUT_SERVICE", "all"))
    root = Path.cwd().resolve()
    for item in selected:
        folder = (root / item["directory"]).resolve()
        dockerfile = (root / item["dockerfile"]).resolve()
        if not (folder.is_dir() and dockerfile.is_file() and
                folder != root and folder.is_relative_to(root) and
                dockerfile.is_relative_to(folder)):
            raise SystemExit("invalid_owned_build_context:" + item["service"])
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write("matrix=" + json.dumps(selected, separators=(",", ":")) + "\n")
    print(json.dumps({"source_sha": sha, "selected": selected}, sort_keys=True))

if __name__ == "__main__":
    main()
