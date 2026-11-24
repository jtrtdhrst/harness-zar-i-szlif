#!/usr/bin/env python3
"""Retire stale flow pages only when their source file is absent from Git HEAD.

The index-only update already tombstones deleted file pages but can retain
source-keyed flow pages as stale. Re-generating them cannot work: the source no
longer exists. Preserve the row and its provenance as a tombstone instead.
"""
import argparse
import datetime
import json
import sqlite3
import subprocess
from pathlib import Path

SOURCE_SUFFIXES = frozenset((".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".go", ".rs"))
REPOS = frozenset(("harness", "product"))


def source_deleted(repo_root, target):
    file_part = target.split("::", 1)[0]
    rel = Path(file_part)
    if (not file_part or "::" not in target or rel.is_absolute()
            or ".." in rel.parts or rel.suffix.lower() not in SOURCE_SUFFIXES):
        return False
    full = repo_root / rel
    if full.exists():
        return False
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo_root}", "-C", str(repo_root),
         "ls-tree", "-r", "--name-only", "HEAD", "--", file_part],
        capture_output=True, text=True, check=False, timeout=5,
    )
    # Exit=0 is essential: a broken repository must never be interpreted as
    # evidence of a deleted source. No stdout means absent from committed HEAD.
    return result.returncode == 0 and not result.stdout.strip()


def eligible_orphans(connection, repo_root):
    rows = connection.execute(
        "SELECT id, target_path, metadata_json FROM wiki_pages "
        "WHERE page_type='flow_page' AND freshness_status='stale'"
    ).fetchall()
    return [(pid, target, meta) for pid, target, meta in rows
            if source_deleted(repo_root, target)]


def retire(db_path, repo_root, apply=False):
    con = sqlite3.connect(str(db_path), timeout=25)
    try:
        con.execute("PRAGMA busy_timeout=25000")
        rows = eligible_orphans(con, repo_root)
        if apply and rows:
            con.execute("BEGIN IMMEDIATE")
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            for pid, _, raw_meta in rows:
                try:
                    meta = json.loads(raw_meta or "{}")
                except (ValueError, TypeError):
                    meta = {}
                if not isinstance(meta, dict):
                    meta = {}
                meta.update(tombstone_reason="deleted",
                            successor_paths=[], tombstoned_at=now)
                cur = con.execute(
                    "UPDATE wiki_pages SET freshness_status='tombstone', metadata_json=? "
                    "WHERE id=? AND page_type='flow_page' AND freshness_status='stale'",
                    (json.dumps(meta, sort_keys=True), pid)
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"row changed during retirement: {pid}")
            con.commit()
        return [pid for pid, _, _ in rows]
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", choices=sorted(REPOS))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path("/workspace") / args.repo
    ids = retire(root / ".repowise" / "wiki.db", root, args.apply)
    print(json.dumps({"repo": args.repo, "mode": "apply" if args.apply else "dry_run",
                      "retired": len(ids), "ids": ids}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
