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


class WriterRevocation(unittest.TestCase):
    def test_absent_writer_does_not_create_a_credential(self):
        import tempfile
        from unittest.mock import patch
        project = load("github-ops-token-project.py", "bgh_projector_absent")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'writer.json'
            with patch.object(project, 'WRITER_TARGET', target):
                self.assertFalse(project.retire_writer_target())
                self.assertFalse(target.exists())

    def test_stale_writer_is_removed_only_for_exact_safe_identity(self):
        import tempfile
        import stat
        from types import SimpleNamespace
        from unittest.mock import patch
        project = load("github-ops-token-project.py", "bgh_projector_safe")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'writer.json'
            target.write_text('synthetic-marker')
            target.chmod(0o640)
            existing = target.lstat()
            trusted = SimpleNamespace(st_mode=existing.st_mode, st_uid=0,
                st_gid=project.NODE_GID, st_nlink=1)
            with patch.object(project, 'WRITER_TARGET', target), patch.object(project.os, 'lstat', return_value=trusted):
                self.assertTrue(project.retire_writer_target())
            self.assertFalse(target.exists())

    def test_untrusted_projected_writer_is_never_deleted(self):
        import tempfile
        from unittest.mock import patch
        project = load("github-ops-token-project.py", "bgh_projector_untrusted")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'writer.json'
            target.write_text('unchanged')
            target.chmod(0o644)
            with patch.object(project, 'WRITER_TARGET', target):
                with self.assertRaisesRegex(RuntimeError, 'Untrusted projected writer'):
                    project.retire_writer_target()
            self.assertEqual(target.read_text(), 'unchanged')


if __name__ == "__main__":
    unittest.main()
