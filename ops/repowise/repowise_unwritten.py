#!/usr/bin/env python3
"""List model-eligible RepoWise pages that are unwritten or need refreshing.

Without --pending, preserve legacy unwritten-only behavior.
Populated deterministic onboarding pages are not model stubs.
"""
import sqlite3
from datetime import datetime, timezone
import sys
from pathlib import Path

MODEL_TYPES = "('module_page', 'flow_page', 'repo_overview', 'onboarding')"
UNWRITTEN = """
  (coalesce(model_name, '') = ''
   AND NOT (id = 'onboarding:onboarding/active_landscape'
            AND length(trim(coalesce(content, ''))) > 0))
"""
PENDING = f"""
SELECT id FROM wiki_pages
WHERE page_type IN {MODEL_TYPES}
  AND freshness_status != 'tombstone'
  AND ({UNWRITTEN}
       OR (freshness_status = 'stale' AND coalesce(model_name, '') != ''))
ORDER BY id
"""
SQL = f"""
SELECT id FROM wiki_pages
WHERE page_type IN {MODEL_TYPES}
  AND freshness_status != 'tombstone'
  AND {UNWRITTEN}
ORDER BY id
"""

def pending_pages(db_path, include_stale=False, indexed_at=None):
    with sqlite3.connect(str(db_path)) as connection:
        rows = [row[0] for row in connection.execute(PENDING if include_stale else SQL)]
        if indexed_at is None or not include_stale:
            return rows
        indexed_time = datetime.fromisoformat(indexed_at)
        if indexed_time.tzinfo is None:
            indexed_time = indexed_time.replace(tzinfo=timezone.utc)
        pending = []
        for page_id in rows:
            record = connection.execute(
                'SELECT freshness_status, model_name, updated_at FROM wiki_pages WHERE id=?',
                (page_id,),
            ).fetchone()
            if record and record[0] == 'stale' and record[1] and record[2]:
                updated_time = datetime.fromisoformat(record[2])
                if updated_time.tzinfo is None:
                    updated_time = updated_time.replace(tzinfo=timezone.utc)
                if updated_time >= indexed_time:
                    continue
            pending.append(page_id)
        return pending

def main(argv):
    if len(argv) not in (2, 3) or argv[1] not in ('product', 'harness') or (len(argv) == 3 and argv[2] != '--pending'):
        print('usage: repowise_unwritten.py product|harness [--pending]', file=sys.stderr)
        return 2
    indexed_at = None
    if len(argv) == 3:
        import yaml
        workspace = yaml.safe_load(Path('/workspace/.repowise-workspace.yaml').read_text())
        indexed_at = next(
            (item.get('indexed_at') for item in workspace['repos'] if item.get('alias') == argv[1]),
            None,
        )
        if not indexed_at:
            print('missing workspace indexed_at for repo', file=sys.stderr)
            return 1
    for page_id in pending_pages(
        Path('/workspace') / argv[1] / '.repowise/wiki.db',
        include_stale=(len(argv) == 3),
        indexed_at=indexed_at,
    ):
        print(page_id)
    return 0

if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
