#!/usr/bin/env python3
"""Report whether live RepoWise checkouts match the last fetched GitHub main.

RepoWise's own `index_behind` compares the index with its mounted checkout, so a
stale checkout makes a stale index look healthy. This checker uses the SHA that
the sync fetched from GitHub instead, and fails when that evidence is missing,
old, or does not match both live checkouts.
"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

REPOS = ("product", "harness")


def evaluate(status, heads, now, max_age):
    errors = []
    if not status:
        return ["missing github-main.json"]
    try:
        fetched = datetime.datetime.fromisoformat(status["fetched_at"])
    except (KeyError, TypeError, ValueError):
        return ["invalid fetched_at in github-main.json"]
    if (now - fetched).total_seconds() > max_age:
        errors.append(f"github-main.json is older than {max_age}s")
    for repo in REPOS:
        expected = status.get(repo)
        if not expected:
            errors.append(f"github-main.json has no {repo} SHA")
        elif heads.get(repo) != expected:
            errors.append(f"{repo} live={heads.get(repo)} expected={expected}")
    return errors


def read_head(path):
    result = subprocess.run(
        ["git", "-c", f"safe.directory={path}", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", default="/opt/repowise-knowledge/github-main.json")
    parser.add_argument("--live", default="/var/lib/docker/volumes/oea9obpkhzbgkmipxwqmz2hj-repowise-workspace/_data")
    parser.add_argument("--max-age", type=int, default=1800)
    args = parser.parse_args(argv)

    try:
        status = json.loads(Path(args.status).read_text())
    except (OSError, json.JSONDecodeError):
        status = None
    heads = {repo: read_head(Path(args.live) / repo) for repo in REPOS}
    errors = evaluate(status, heads, datetime.datetime.now(datetime.timezone.utc), args.max_age)
    print(json.dumps({"heads": heads, "status": status, "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
