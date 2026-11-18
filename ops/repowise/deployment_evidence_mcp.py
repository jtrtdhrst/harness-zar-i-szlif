#!/usr/bin/env python3
"""Least-privilege RepoWise deployment evidence publisher.

Writes shareable, explicitly partial observations into the existing native
RepoWise EpisodeStore. Never grants deployment approval or executes deployments.
The stdio MCP transport is intentionally private to a trusted caller.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from repowise.core.precedent.store import Episode, EpisodeStore, TIER_GIT, default_store_path

ROOT = Path(os.environ.get("DEPLOY_EVIDENCE_ROOT", "/workspace")).resolve()
REPOS = {"product": "product", "harness": "harness"}
SHA = re.compile(r"^[0-9a-f]{40}$")
ISSUE = re.compile(r"^ZARI-[1-9][0-9]{0,6}$")
IDENTIFIER = re.compile(r"^[a-zA-Z0-9_-]{3,80}$")
PUBLIC_RELEASE = "https://panel.zariszlif.pl/__release.json"
PUBLIC_HEALTH = "https://panel.zariszlif.pl/healthz"
mcp = FastMCP("repowise-deployment-evidence", instructions=(
    "Record source-verified deployment observations into RepoWise episodes; "
    "PARTIAL status is not production E2E. No arbitrary paths, URLs or hosts."))


def _git_contains(path: Path, sha: str) -> bool:
    r = subprocess.run(
        ["git", "-C", str(path), "cat-file", "-e", sha + "^{commit}"],
        capture_output=True, timeout=5, check=False,
    )
    return r.returncode == 0


def _live_product() -> tuple[str | None, int | None]:
    try:
        request = urllib.request.Request(
            PUBLIC_RELEASE, headers={"User-Agent": "RepowiseEvidence/1", "Cache-Control": "no-cache"}
        )
        with urllib.request.urlopen(request, timeout=7) as r:
            marker = json.load(r)
        with urllib.request.urlopen(PUBLIC_HEALTH, timeout=7) as r:
            code = r.status
        if marker.get("source") != "zar-i-szlif/main":
            return None, code
        live = marker.get("commit")
        return (live if isinstance(live, str) and SHA.fullmatch(live) else None), code
    except (OSError, ValueError, TimeoutError, urllib.error.HTTPError):
        return None, None


def _path(repo: str) -> Path:
    if repo not in REPOS:
        raise ValueError("repo_not_allowed")
    # Only the operator can assign this identity through the process env.
    # Never infer repository write authority from an agent-supplied argument.
    assigned = os.environ.get("DEPLOY_EVIDENCE_ALLOWED_REPO", "").strip()
    if assigned not in REPOS:
        raise ValueError("server_repo_scope_missing")
    if repo != assigned:
        raise ValueError("repo_out_of_scope")
    path = (ROOT / REPOS[repo]).resolve()
    if not path.is_relative_to(ROOT) or not (path / ".repowise").is_dir():
        raise ValueError("indexed_repo_unavailable")
    return path


def report(repo: str, source_sha: str, issue: str, deployment_id: str) -> dict:
    if not isinstance(source_sha, str) or not SHA.fullmatch(source_sha):
        raise ValueError("invalid_source_sha")
    if not isinstance(issue, str) or not ISSUE.fullmatch(issue):
        raise ValueError("invalid_issue")
    if not isinstance(deployment_id, str) or not IDENTIFIER.fullmatch(deployment_id):
        raise ValueError("invalid_deployment_id")
    path = _path(repo)
    if not _git_contains(path, source_sha):
        raise ValueError("source_sha_not_present_in_indexed_repo")
    live_sha, health = _live_product() if repo == "product" else (None, None)
    if repo == "product" and (live_sha != source_sha or health != 200):
        raise ValueError("production_readback_not_matching_source")
    # This is a runtime observation only. An agent cannot self-assert an
    # independent QA test, approved merge, immutable digest or rollback.
    status = "PARTIAL_LIVE_OBSERVED" if repo == "product" else "SOURCE_ONLY_NOT_LIVE_VERIFIED"
    subject = f"deployment:{repo}:{source_sha}:{deployment_id}:{issue}"
    evidence = {
        "schema": 1, "source": "trusted-host-observation",
        "status": status, "repo": repo, "source_sha": source_sha,
        "issue": issue, "deployment_id": deployment_id,
        "live_source_sha": live_sha, "public_health_http": health,
        "immutable_digest": "NOT_VERIFIED",
        "independent_authenticated_positive_qa": "NOT_RUN",
        "independent_authenticated_negative_qa": "NOT_RUN",
        "rollback": "NOT_RUN",
    }
    ep = Episode(
        tier=TIER_GIT, kind="deployment_observation", subject=subject,
        body=json.dumps(evidence, sort_keys=True, ensure_ascii=False),
        evidence=f"source=git,live_release={PUBLIC_RELEASE if repo == 'product' else 'NOT_RUN'}",
        nodes=(), birth_commit=source_sha,
    )
    store = EpisodeStore(default_store_path(path))
    try:
        prior = store.get_episode(ep.id, tiers=(TIER_GIT,))
        if prior is None:
            store.append_tier(tier=TIER_GIT, episodes=[ep])
        elif prior["body"] != ep.body:
            raise ValueError("immutable_id_conflict")
        found = store.get_episode(ep.id, tiers=(TIER_GIT,))
        if not found or found["body"] != ep.body:
            raise RuntimeError("readback_mismatch")
    finally:
        store.close()
    return {"stored": True, "created": prior is None, "episode_id": ep.id, **evidence}


@mcp.tool()
def publish_deployment_observation(repo: str, source_sha: str, issue: str, deployment_id: str) -> dict:
    """Store a source-verified, partial deployment observation in native RepoWise.

    This does NOT mark deployment verified E2E or authorize a release.
    Sources are fixed Git checkouts and HTTPS production readbacks.
    """
    try:
        return report(repo, source_sha, issue, deployment_id)
    except (ValueError, RuntimeError) as exc:
        return {"stored": False, "error": str(exc)}


@mcp.tool()
def get_deployment_observation(repo: str, episode_id: str) -> dict:
    """Read back a native RepoWise episode by its immutable ID."""
    if not re.fullmatch(r"[0-9a-f]{16}", episode_id or ""):
        return {"found": False, "error": "invalid_episode_id"}
    try:
        path = _path(repo)
        db_path = default_store_path(path)
        if not db_path.is_file():
            return {"found": False}
        store = EpisodeStore(db_path)
        try:
            row = store.get_episode(episode_id, tiers=(TIER_GIT,))
        finally:
            store.close()
        if not row or row.get("kind") != "deployment_observation":
            return {"found": False}
        return {"found": True, "episode_id": episode_id, "evidence": json.loads(row["body"])}
    except (ValueError, OSError) as exc:
        return {"found": False, "error": str(exc)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--repo", default="product")
    parser.add_argument("--sha", default="")
    parser.add_argument("--issue", default="ZARI-240")
    parser.add_argument("--deployment", default="observed-release")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(report(args.repo, args.sha, args.issue, args.deployment), sort_keys=True))
    else:
        mcp.run(transport="stdio")
