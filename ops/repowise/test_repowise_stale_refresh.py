import sqlite3
import tempfile
import unittest
from pathlib import Path

from repowise_unwritten import pending_pages


class PendingRefreshTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'wiki.db'
        with sqlite3.connect(str(self.db)) as c:
            c.execute('CREATE TABLE wiki_pages (id TEXT, page_type TEXT, model_name TEXT, content TEXT, freshness_status TEXT)')
            c.executemany('INSERT INTO wiki_pages VALUES (?,?,?,?,?)', [
                ('onboarding:onboarding/active_landscape', 'onboarding', '', '# Git-derived', 'stale'),
                ('onboarding:onboarding/getting_started', 'onboarding', 'deepseek-v4.1-flash', 'old text', 'stale'),
                ('onboarding:onboarding/how_it_works', 'onboarding', 'deepseek-v4.1-flash', 'new text', 'fresh'),
                ('repo_overview:product', 'repo_overview', 'deepseek-v4.1-flash', 'old text', 'stale'),
                ('module_page:missing', 'module_page', '', '', 'fresh'),
                ('file_page:src/x.ts', 'file_page', '', 'structural data', 'stale'),
            ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_unwritten_only_remains_backward_compatible(self):
        self.assertEqual(pending_pages(self.db), ['module_page:missing'])

    def test_pending_includes_unwritten_and_stale_model_pages(self):
        self.assertEqual(pending_pages(self.db, include_stale=True), [
            'module_page:missing',
            'onboarding:onboarding/getting_started',
            'repo_overview:product',
        ])

    def test_empty_deterministic_page_can_be_rebuilt(self):
        with sqlite3.connect(str(self.db)) as c:
            c.execute("UPDATE wiki_pages SET content='  ' WHERE id='onboarding:onboarding/active_landscape'")
        self.assertIn('onboarding:onboarding/active_landscape',
                      pending_pages(self.db, include_stale=True))

    def test_fresh_model_pages_and_structural_pages_do_not_recur(self):
        self.assertNotIn('onboarding:onboarding/how_it_works',
                         pending_pages(self.db, include_stale=True))
        self.assertNotIn('file_page:src/x.ts',
                         pending_pages(self.db, include_stale=True))


if __name__ == '__main__':
    unittest.main()
