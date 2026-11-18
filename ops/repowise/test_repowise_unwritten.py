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

if __name__ == '__main__':
    unittest.main()
