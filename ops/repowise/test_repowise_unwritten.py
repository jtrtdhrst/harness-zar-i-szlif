import sqlite3
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

if __name__ == "__main__":
    unittest.main()
