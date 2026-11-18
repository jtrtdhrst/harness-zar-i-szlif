#!/usr/bin/env python3
"""List model-eligible RepoWise pages that are unwritten or need refreshing.

Without --pending, preserve legacy unwritten-only behavior.
Populated deterministic onboarding pages are not model stubs.
"""
import sqlite3
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
  AND ({UNWRITTEN}
       OR (freshness_status = 'stale' AND coalesce(model_name, '') != ''))
ORDER BY id
"""
SQL = f"""
SELECT id FROM wiki_pages
WHERE page_type IN {MODEL_TYPES} AND {UNWRITTEN}
ORDER BY id
"""

def pending_pages(db_path, include_stale=False):
    with sqlite3.connect(str(db_path)) as connection:
        return [row[0] for row in connection.execute(PENDING if include_stale else SQL)]

def main(argv):
    if len(argv) not in (2, 3) or argv[1] not in ('product', 'harness') or (len(argv) == 3 and argv[2] != '--pending'):
        print('usage: repowise_unwritten.py product|harness [--pending]', file=sys.stderr)
        return 2
    for page_id in pending_pages(Path('/workspace') / argv[1] / '.repowise/wiki.db', include_stale=(len(argv) == 3)):
        print(page_id)
    return 0

if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
