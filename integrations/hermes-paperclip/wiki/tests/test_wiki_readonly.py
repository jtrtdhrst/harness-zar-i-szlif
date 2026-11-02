"""Unit tests for the read-only Hermes Test Markdown Wiki MCP."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "wiki_readonly.py"
SPEC = importlib.util.spec_from_file_location("wiki_readonly", MODULE)
wiki = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wiki)

class WikiReadOnlyTests(unittest.TestCase):
    def test_canonical_page_and_hash(self):
        data = wiki.wiki_read("wiki/concepts/karta-zbiorki.md")
        self.assertEqual(data["sha256"], "27279ffd7450b58f2c0083958982232ca105e35d02f54c5b099057179850c0ba")
        self.assertTrue(data["read_only"])

    def test_lists_only_markdown(self):
        data = wiki.wiki_list(limit=200)
        self.assertGreaterEqual(data["returned"], 100)
        self.assertTrue(all(page["path"].endswith(".md") for page in data["pages"]))

    def test_search(self):
        data = wiki.wiki_search("Karta Zbiórki", limit=10)
        self.assertGreater(data["returned"], 0)

    def test_rejects_traversal(self):
        for path in ("/etc/passwd", "../secrets/x.md", "../../etc/shadow.md", "wiki/concepts/karta-zbiorki.txt", ""):
            with self.subTest(path=path), self.assertRaises(ValueError):
                wiki.wiki_read(path)

    def test_rejects_bad_query(self):
        with self.assertRaises(ValueError): wiki.wiki_search("")

    def test_read_not_outside_wiki(self):
        with self.assertRaises(ValueError): wiki.wiki_read("not-an-existing-file.md")

if __name__ == "__main__":
    unittest.main()
