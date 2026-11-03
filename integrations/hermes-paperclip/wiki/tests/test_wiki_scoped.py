"""Profile-scoped Paperclip Wiki MCP authorization tests.

Run inside the Hermes container (mcp dependency and Wiki snapshot required):
  HERMES_HOME=/opt/data/profiles/cho /opt/hermes/.venv/bin/python -m unittest -v \
    /opt/data/mcp/tests/test_wiki_scoped.py
"""
import runpy
import sys
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "wiki_scoped.py"
WIKI = Path("/opt/data/wiki-paperclip-test/wiki/concepts/karta-zbiorki.md")


def load_profile(name):
    previous = sys.argv
    try:
        sys.argv = [str(MODULE), "--profile", name]
        return runpy.run_path(str(MODULE), run_name="test_scoped_wiki")
    finally:
        sys.argv = previous


@unittest.skipUnless(WIKI.is_file(), "Requires live read-only Paperclip Wiki snapshot")
class ScopedWikiTests(unittest.TestCase):
    def test_shared_page_is_readable_for_all(self):
        for profile in ("ceo", "cho", "cpo", "mascot-designer"):
            with self.subTest(profile=profile):
                wiki = load_profile(profile)
                data = wiki["wiki_read"]("wiki/concepts/karta-zbiorki.md")
                self.assertEqual(len(data["sha256"]), 64)
                self.assertTrue(data["read_only"])

    def test_other_agent_instructions_denied(self):
        for profile in ("cho", "cpo", "mascot-designer"):
            with self.subTest(profile=profile):
                wiki = load_profile(profile)
                with self.assertRaises(ValueError):
                    wiki["wiki_read"]("wiki/agents/ceo/AGENTS.md")

    def test_agent_owns_own_instructions(self):
        wiki = load_profile("ceo")
        own = wiki["wiki_read"]("wiki/agents/ceo/AGENTS.md")
        self.assertEqual(own["path"], "wiki/agents/ceo/AGENTS.md")

    def test_harness_path_only_for_harness_roles(self):
        self.assertTrue(load_profile("cho")["_allowed"]("wiki/agents/harness/AGENTS.md"))
        self.assertFalse(load_profile("cpo")["_allowed"]("wiki/agents/harness/AGENTS.md"))

    def test_legacy_archives_and_traversal_denied(self):
        wiki = load_profile("ceo")
        for path in (
            "wiki/context-archives/ceo/AGENTS-2026-10-20.md",
            "../secrets/keys.md",
            "/etc/passwd",
            "wiki/concepts/karta-zbiorki.txt",
            "",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                wiki["wiki_read"](path)

    def test_list_and_search_do_not_leak_other_role(self):
        wiki = load_profile("cho")
        listed = wiki["wiki_list"](limit=200)
        self.assertGreater(listed["returned"], 30)
        self.assertTrue(all(not item["path"].startswith("wiki/agents/ceo/")
                            for item in listed["pages"]))
        matched = wiki["wiki_search"]("AGENTS", limit=30)
        self.assertTrue(all(not item["path"].startswith("wiki/agents/ceo/")
                            for item in matched["matches"]))

    def test_missing_profile_arg_rejected(self):
        old = sys.argv
        try:
            sys.argv = [str(MODULE)]
            with self.assertRaises(SystemExit) as caught:
                runpy.run_path(str(MODULE), run_name="test_missing_profile")
            self.assertNotEqual(caught.exception.code, 0)
        finally:
            sys.argv = old


if __name__ == "__main__":
    unittest.main()
