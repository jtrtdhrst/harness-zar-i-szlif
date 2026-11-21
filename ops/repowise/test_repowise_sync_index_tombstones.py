#!/usr/bin/env python3
"""Tombstones survive in SQL, but must not pollute live RepoWise FTS."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name("repowise_sync_index.py")
spec = importlib.util.spec_from_file_location("repowise_index_under_test", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
SHA = "a" * 40


class TombstoneFTSContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "wiki.db"
        self.db = sqlite3.connect(self.path)
        self.db.execute("CREATE TABLE repositories (id TEXT,name TEXT,local_path TEXT,head_commit TEXT)")
        self.db.execute("INSERT INTO repositories VALUES (?,?,?,?)", ("r1", "harness", "/workspace/harness", SHA))
        self.db.execute("CREATE TABLE wiki_pages (id TEXT,repository_id TEXT,title TEXT,content TEXT,summary TEXT,target_path TEXT,metadata_json TEXT,digest TEXT,freshness_status TEXT)")
        self.db.execute("CREATE TABLE wiki_symbols (repository_id TEXT)")
        self.db.execute(mod.FTS_DDL)
        self.addCleanup(self.db.close)

    def insert(self, page_id, status):
        self.db.execute("INSERT INTO wiki_pages VALUES (?,?,?,?,?,?,?,?,?)",
                        (page_id, "r1", "Source " + page_id, "source body", "", page_id, "{}", "", status))

    def rebuild(self):
        self.db.execute(mod.FTS_INSERT, ("r1",))
        self.db.commit()

    def test_fts_excludes_tombstones_but_keeps_null_legacy(self):
        self.insert("active", "fresh")
        self.insert("historical", "tombstone")
        self.insert("legacy", None)
        self.rebuild()
        self.assertEqual({r[0] for r in self.db.execute("SELECT page_id FROM page_fts")},
                         {"active", "legacy"})
        result = mod.check_wiki(self.path, "harness", SHA, full=False)
        self.assertEqual(result["pages"], 2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0], 3)

    def test_missing_active_fts_still_rejected(self):
        self.insert("active", "fresh")
        self.insert("historical", "tombstone")
        self.db.commit()
        with self.assertRaisesRegex(RuntimeError, "page/FTS mismatch"):
            mod.check_wiki(self.path, "harness", SHA, full=False)

    def test_orphaned_retired_fts_still_rejected(self):
        self.insert("active", "fresh")
        self.insert("historical", "tombstone")
        self.rebuild()
        self.db.execute("INSERT INTO page_fts(page_id,title) VALUES (?,?)", ("historical", "old"))
        self.db.commit()
        with self.assertRaisesRegex(RuntimeError, "page/FTS mismatch"):
            mod.check_wiki(self.path, "harness", SHA, full=False)


if __name__ == "__main__":
    unittest.main()
