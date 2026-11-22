#!/usr/bin/env python3
"""Select reviewed MCP image build contexts for trusted-main GitHub Actions.

This only selects/builds OCI artifacts. It cannot authorize promotion or clear
Coolify service HOLDs. No repository path is executed as a shell command.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

# Only source-owned Dockerfiles; externally managed or unpinned images are not
# built from this repository. Keep this table deliberately explicit.
MCP_BUILD_CONTEXTS = {
    "comfy-mcp": "comfy-mcp",
    "emailens-mcp": "emailens-mcp",
    "mantic-mcp": "mantic-mcp",
    "plasmic-mcp": "plasmic-mcp",
    "playwright-mcp": "playwright-mcp",
    "supabase-mcp": "supabase-mcp",
    "ubuntu-mcp": "ubuntu-mcp",
}
BUILD_CONFIG_PATHS = {
    ".github/workflows/mcp-images-ghcr.yml",
    "scripts/select_mcp_builds.py",
}
EXPECTED_REPOSITORY = "jtrtdhrst/harness-zar-i-szlif"


def select(changed_paths, *, event_name, manual_service="all"):
    if event_name == "workflow_dispatch":
        if manual_service == "all":
            selected = set(MCP_BUILD_CONTEXTS)
        elif manual_service in MCP_BUILD_CONTEXTS:
            selected = {manual_service}
        else:
            raise ValueError("invalid_manually_selected_service")
    elif event_name == "push":
        changed_paths = set(changed_paths)
        if changed_paths & BUILD_CONFIG_PATHS:
            selected = set(MCP_BUILD_CONTEXTS)
        else:
            selected = {
                service for service, root in MCP_BUILD_CONTEXTS.items()
                if any(path.startswith(root + "/") for path in changed_paths)
            }
    else:
        raise ValueError("untrusted_event")
    return [{"service": service, "directory": MCP_BUILD_CONTEXTS[service],
             "dockerfile": "Dockerfile.http" if service == "mantic-mcp" else "Dockerfile"}
            for service in sorted(selected)]


def main():
    if (os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_REPOSITORY") != EXPECTED_REPOSITORY):
        raise SystemExit("untrusted_repository_or_branch")
    event_name = os.environ["GITHUB_EVENT_NAME"]
    sha = os.environ["GITHUB_SHA"]
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if actual != sha:
        raise SystemExit("checkout_source_sha_mismatch")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    if event_name == "push":
        before = event.get("before", "")
        if before and before != "0" * 40:
            # Checkout uses fetch-depth: 0, so the exact event range is present.
            changed = subprocess.check_output(
                ["git", "diff", "--name-only", "--no-renames", before, sha],
                text=True).splitlines()
        else:
            changed = list(BUILD_CONFIG_PATHS)  # first push: safe full build
    else:
        changed = []
    selected = select(changed, event_name=event_name,
                      manual_service=os.environ.get("INPUT_SERVICE", "all"))
    for item in selected:
        folder = Path(item["directory"])
        if not (folder / item["dockerfile"]).is_file():
            raise SystemExit("missing_dockerfile:" + item["service"])
    value = json.dumps(selected, separators=(",", ":"))
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write("matrix=" + value + "\n")
    print(json.dumps({"source_sha": sha, "selected": selected}, sort_keys=True))


if __name__ == "__main__":
    main()
