"""Offline regression tests for the committed RepoWise orphan-flow retirement helper."""
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import repowise_retire_orphan_flows as helper

class RetireOrphansTests(unittest.TestCase):
    def test_no_git_or_invalid_target_is_never_retired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for target in ("../outside.py::call", "/etc/passwd::call", "README.md::call", "foo.py"):
                self.assertFalse(helper.source_deleted(root,target))
            self.assertFalse(helper.source_deleted(root,"src/missing.py::call"))

    def test_deleted_file_tombstones_and_preserves_existing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            subprocess.run(["git","init","-q"],cwd=root,check=True)
            subprocess.run(["git","config","user.email","test@example.invalid"],cwd=root,check=True)
            subprocess.run(["git","config","user.name","Test"],cwd=root,check=True)
            (root/"live.py").write_text("print(1)\n")
            subprocess.run(["git","add","live.py"],cwd=root,check=True)
            subprocess.run(["git","commit","-qm","baseline"],cwd=root,check=True)
            db=root/"wiki.db"
            con=sqlite3.connect(db)
            con.execute("CREATE TABLE wiki_pages (id INTEGER PRIMARY KEY, target_path TEXT, metadata_json TEXT, page_type TEXT, freshness_status TEXT)")
            con.executemany("INSERT INTO wiki_pages VALUES (?,?,?,?,?)", [
                (1,"gone.py::function",json.dumps({"preserve":"yes"}),"flow_page","stale"),
                (2,"live.py::function","{}","flow_page","stale"),
                (3,"gone.ts::function","{}","flow_page","fresh"),
            ])
            con.commit()
            con.close()
            self.assertEqual(helper.retire(db,root,apply=False),[1])
            with sqlite3.connect(db) as con:
                self.assertEqual(con.execute("SELECT freshness_status FROM wiki_pages WHERE id=1").fetchone()[0],"stale")
            self.assertEqual(helper.retire(db,root,apply=True),[1])
            with sqlite3.connect(db) as con:
                status, meta = con.execute("SELECT freshness_status,metadata_json FROM wiki_pages WHERE id=1").fetchone()
                self.assertEqual(status,"tombstone")
                data=json.loads(meta)
                self.assertEqual(data["preserve"],"yes")
                self.assertEqual(data["tombstone_reason"],"deleted")
                self.assertEqual(con.execute("SELECT freshness_status FROM wiki_pages WHERE id=2").fetchone()[0],"stale")
                self.assertEqual(con.execute("SELECT freshness_status FROM wiki_pages WHERE id=3").fetchone()[0],"fresh")

if __name__=="__main__":
    unittest.main()
