#!/usr/bin/env python3
"""List genuinely unwritten model pages; skip populated deterministic pages."""
import sqlite3
import sys
from pathlib import Path

SQL = """
SELECT id FROM wiki_pages
WHERE page_type IN ('module_page', 'flow_page', 'repo_overview', 'onboarding')
  AND model_name = ''
  AND NOT (
    id = 'onboarding:onboarding/active_landscape'
    AND length(trim(coalesce(content, ''))) > 0
  )
ORDER BY id
"""

def pending_pages(db_path):
    with sqlite3.connect(str(db_path)) as connection:
        return [row[0] for row in connection.execute(SQL).fetchall()]

def main(argv):
    if len(argv) != 2 or argv[1] not in ('product', 'harness'):
        print('usage: repowise_unwritten.py product|harness', file=sys.stderr)
        return 2
    for page_id in pending_pages(Path('/workspace') / argv[1] / '.repowise/wiki.db'):
        print(page_id)
    return 0

if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
