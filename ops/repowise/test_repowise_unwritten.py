import sqlite3
import tempfile
import unittest
from pathlib import Path

from repowise_unwritten import pending_pages

class UnwrittenPagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'wiki.db'
        with sqlite3.connect(str(self.db)) as c:
            c.execute('CREATE TABLE wiki_pages (id TEXT, page_type TEXT, model_name TEXT, content TEXT)')
            c.executemany('INSERT INTO wiki_pages VALUES (?,?,?,?)', [
                ('onboarding:onboarding/active_landscape', 'onboarding', '', '# Generated from git'),
                ('onboarding:onboarding/how_it_works', 'onboarding', '', ''),
                ('flow:example', 'flow_page', 'some-model', 'Done'),
            ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_excludes_populated_deterministic_page(self):
        self.assertEqual(pending_pages(self.db), ['onboarding:onboarding/how_it_works'])

    def test_includes_empty_deterministic_page(self):
        with sqlite3.connect(str(self.db)) as c:
            c.execute("UPDATE wiki_pages SET content='  ' WHERE id='onboarding:onboarding/active_landscape'")
        self.assertEqual(pending_pages(self.db), [
            'onboarding:onboarding/active_landscape',
            'onboarding:onboarding/how_it_works'
        ])


    def test_pending_regenerates_stale_once_per_revision(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / 'wiki.db'
            with sqlite3.connect(str(db)) as c:
                c.execute('CREATE TABLE wiki_pages (id TEXT, page_type TEXT, model_name TEXT, content TEXT, freshness_status TEXT, updated_at TEXT)')
                c.executemany('INSERT INTO wiki_pages VALUES (?,?,?,?,?,?)', [
                    ('module_page:stale', 'module_page', 'model', 'old', 'stale', '2026-11-17 10:00:00'),
                    ('onboarding:updated', 'onboarding', 'model', 'new', 'stale', '2026-11-18 10:00:00'),
                    ('onboarding:onboarding/active_landscape', 'onboarding', '', 'structural', 'stale', '2026-11-17 10:00:00'),
                    ('module_page:stub', 'module_page', '', '', 'fresh', '2026-11-17 10:00:00'),
                    ('file_page:structural', 'file_page', 'model', 'structural', 'stale', '2026-11-17 10:00:00'),
                ])
            self.assertEqual(pending_pages(db, include_stale=True, indexed_at='2026-11-17T22:00:00+00:00'),
                             ['module_page:stale', 'module_page:stub'])
            self.assertEqual(pending_pages(db, include_stale=True, indexed_at='2026-11-18T11:00:00+00:00'),
                             ['module_page:stale', 'module_page:stub', 'onboarding:updated'])


if __name__ == '__main__':
    unittest.main()
