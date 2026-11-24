#!/usr/bin/env python3
"""List model-eligible RepoWise pages that are unwritten or need refreshing.

Without --pending, preserve legacy unwritten-only behavior.
Populated deterministic onboarding pages are not model stubs.
"""
import sqlite3
import subprocess
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

def _is_production_code(path):
    """Prefer RepoWise's own classification, with a local-test fallback."""
    try:
        from repowise.core.support_paths import file_population, is_support_path
        from repowise.core.test_paths import is_test_related_path
        return (file_population(path, is_test=is_test_related_path(path))
                == "production" and not is_support_path(path))
    except ImportError:
        from pathlib import PurePosixPath
        parts = PurePosixPath(path).parts
        suffix = PurePosixPath(path).suffix.lower()
        excluded = {"tests", "test", "__tests__", "docs", "examples",
                    "fixtures", "node_modules", "build", "dist"}
        return (not any(part.lower() in excluded for part in parts)
                and suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs",
                               ".cjs", ".go", ".rs", ".java", ".php",
                               ".sh", ".sql", ".css", ".rb", ".vue", ".svelte"}
                and not any(tag in PurePosixPath(path).name.lower()
                            for tag in (".test.", ".spec.", "_test.")))


def _code_changed_after_page(db_path, updated_time):
    """Compare committed source trees, not the indexing clock.

    A later docs-only commit must not perpetually regenerate a deterministic
    git-history page. Diff the first-parent tree at its last generation time
    against HEAD, so old feature commits merged later are still detected.
    """
    root = Path(db_path).resolve().parent.parent
    if not (root / ".git").exists():
        # Legacy isolated wiki.db fixtures have no Git checkout.
        return True

    prefix = ["git", "-c", f"safe.directory={root}", "-C", str(root)]
    def git(*args):
        result = subprocess.run([*prefix, *args], capture_output=True, text=True,
                                check=False, timeout=45)
        if result.returncode:
            raise RuntimeError("RepoWise source freshness git read failed")
        return result.stdout.strip()

    before = updated_time.astimezone(timezone.utc).isoformat()
    base = git("rev-list", "-1", "--first-parent", f"--before={before}", "HEAD")
    paths = (git("diff", "--name-only", base, "HEAD") if base
             else git("ls-tree", "-r", "--name-only", "HEAD"))
    return any(_is_production_code(path) for path in paths.splitlines() if path)


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
        # Deterministic onboarding content has no model_name and RepoWise can
        # leave it marked "fresh" after an index-only GitHub sync. An older page
        # must be re-rendered once for each newer indexed revision.
        deterministic_id = 'onboarding:onboarding/active_landscape'
        record = connection.execute(
            'SELECT freshness_status, model_name, content, updated_at '
            'FROM wiki_pages WHERE id=?', (deterministic_id,),
        ).fetchone()
        if record and record[0] != 'tombstone' and not (record[1] or '').strip():
            if (record[2] or '').strip():
                updated_at = record[3]
                if not updated_at:
                    pending.append(deterministic_id)
                else:
                    updated_time = datetime.fromisoformat(updated_at)
                    if updated_time.tzinfo is None:
                        updated_time = updated_time.replace(tzinfo=timezone.utc)
                    if (updated_time < indexed_time and
                            _code_changed_after_page(db_path, updated_time)):
                        pending.append(deterministic_id)
        return sorted(set(pending))

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
