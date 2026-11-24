#!/usr/bin/env python3
"""Guard exact BGH GitHub App reader/writer role parity without exposing tokens."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent

def load(stem, name):
    spec = importlib.util.spec_from_file_location(name, HERE / stem)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class ProjectionScope(unittest.TestCase):
    def test_reader_projection_matches_minter(self):
        mint = load("multica-zar-github-app-refresh.py", "bgh_minter_reader")
        project = load("github-ops-token-project.py", "bgh_projector_reader")
        self.assertEqual(project.PERMISSIONS, mint.ROLE_PERMISSIONS["github-ops-reader"])
        self.assertEqual(project.ROLE, "github-ops-reader")
        self.assertEqual(project.REPOS, set(mint.REPOS))

    def test_writer_projection_matches_minter_exactly(self):
        mint = load("multica-zar-github-app-refresh.py", "bgh_minter_writer")
        project = load("github-ops-token-project.py", "bgh_projector_writer")
        expected = {"actions":"write", "contents":"write", "pull_requests":"write", "metadata":"read"}
        self.assertEqual(project.WRITER_PERMISSIONS, expected)
        self.assertEqual(project.WRITER_PERMISSIONS, mint.ROLE_PERMISSIONS["github-ops-writer"])
        self.assertEqual(project.WRITER_ROLE, "github-ops-writer")
        self.assertEqual(project.REPOS, set(mint.REPOS))

if __name__ == "__main__":
    unittest.main()
