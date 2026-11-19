import sqlite3
import subprocess
import os
import tempfile
import unittest
from pathlib import Path

from repowise_unwritten import pending_pages

ACTIVE = "onboarding:onboarding/active_landscape"
EMPTY = "onboarding:onboarding/how_it_works"
FLOW = "flow_page:component"

class UnwrittenPagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "wiki.db"
        with sqlite3.connect(self.db) as c:
            c.execute("""CREATE TABLE wiki_pages (
                id TEXT, page_type TEXT, model_name TEXT,
                content TEXT, freshness_status TEXT, updated_at TEXT)""")
            c.executemany("INSERT INTO wiki_pages VALUES (?,?,?,?,?,?)", [
                (ACTIVE, "onboarding", "", "# Historical content", "fresh", "2026-11-18 10:00:00"),
                (EMPTY, "onboarding", "", "", "fresh", "2026-11-18 10:00:00"),
                (FLOW, "flow_page", "model", "Old prose", "stale", "2026-11-18 10:00:00"),
            ])

    def tearDown(self):
        self.tmp.cleanup()

    def pending(self, indexed="2026-11-19T17:00:00+00:00"):
        return pending_pages(self.db, include_stale=True, indexed_at=indexed)

    def test_legacy_does_not_rewrite_populated_deterministic_page(self):
        self.assertEqual(pending_pages(self.db), [EMPTY])

    def test_refreshes_deterministic_page_after_new_index(self):
        self.assertEqual(self.pending(), sorted([ACTIVE, EMPTY, FLOW]))

    def test_skips_deterministic_page_after_refresh(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE wiki_pages SET updated_at=? WHERE id=?",
                      ("2026-11-19 17:00:01", ACTIVE))
        self.assertEqual(self.pending(), sorted([EMPTY, FLOW]))

    def test_skips_tombstone_even_if_old(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE wiki_pages SET freshness_status='tombstone' WHERE id=?", (ACTIVE,))
        self.assertEqual(self.pending(), sorted([EMPTY, FLOW]))

    def test_refreshes_missing_timestamp(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE wiki_pages SET updated_at=NULL WHERE id=?", (ACTIVE,))
        self.assertIn(ACTIVE, self.pending())

    def test_empty_deterministic_page_is_pending_once(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE wiki_pages SET content=' ' WHERE id=?", (ACTIVE,))
        self.assertEqual(self.pending().count(ACTIVE), 1)

    def test_same_index_does_not_requeue_refreshed_model_page(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE wiki_pages SET updated_at='2026-11-19 17:00:01' WHERE id=?", (FLOW,))
        self.assertNotIn(FLOW, self.pending())


class GitBasedDeterministicFreshnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".repowise").mkdir()
        self.db = self.root / ".repowise" / "wiki.db"
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "test@example.com"], check=True)
        with sqlite3.connect(self.db) as c:
            c.execute("""CREATE TABLE wiki_pages (
                id TEXT, page_type TEXT, model_name TEXT, content TEXT,
                freshness_status TEXT, updated_at TEXT)""")
            c.execute("INSERT INTO wiki_pages VALUES (?,?,?,?,?,?)",
                      (ACTIVE, "onboarding", "", "# Historical summary", "fresh",
                       "2026-11-18 10:00:00"))

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, path, timestamp):
        full = self.root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(timestamp)
        subprocess.run(["git", "-C", str(self.root), "add", path], check=True)
        env = dict(os.environ, GIT_AUTHOR_DATE=timestamp, GIT_COMMITTER_DATE=timestamp)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", path],
                       check=True, env=env)

    def pending(self):
        return pending_pages(self.db, include_stale=True,
                             indexed_at="2026-11-19T20:00:00+00:00")

    def test_new_index_without_new_code_is_not_pending(self):
        self.commit("src/before.ts", "2026-11-17T09:00:00+00:00")
        self.assertEqual(self.pending(), [])

    def test_docs_only_commit_does_not_trigger_model_call(self):
        self.commit("src/before.ts", "2026-11-17T09:00:00+00:00")
        self.commit("README.md", "2026-11-19T10:00:00+00:00")
        self.assertEqual(self.pending(), [])

    def test_code_change_triggers_one_refresh(self):
        self.commit("src/before.ts", "2026-11-17T09:00:00+00:00")
        self.commit("src/after.ts", "2026-11-19T11:00:00+00:00")
        self.assertEqual(self.pending(), [ACTIVE])
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE wiki_pages SET updated_at='2026-11-19 12:00:00' WHERE id=?", (ACTIVE,))
        self.assertEqual(self.pending(), [])

    def test_tests_only_commit_does_not_trigger_refresh(self):
        self.commit("src/before.ts", "2026-11-17T09:00:00+00:00")
        self.commit("tests/source.test.ts", "2026-11-19T11:00:00+00:00")
        self.assertEqual(self.pending(), [])

if __name__ == "__main__":
    unittest.main()
