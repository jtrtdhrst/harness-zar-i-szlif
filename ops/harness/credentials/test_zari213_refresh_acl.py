#!/usr/bin/env python3
"""Negative security regressions for root-only GitHub App token refresh paths.

No real provider calls, token reads, or persistent system paths are used.
Execute as a non-root test user. UID-0 ownership is simulated in fstat only.
"""
import importlib.util
import os
import pathlib
import stat
import tempfile
import types
import unittest
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).with_name("multica-zar-github-app-refresh.py")
spec = importlib.util.spec_from_file_location("refresh_acl_under_test", SOURCE)
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


class SafeRefreshPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent = pathlib.Path(self.tmp.name) / "etc-multica-git-credential"
        self.parent.mkdir(mode=0o700)
        self.target = self.parent / "roles"
        self.original_fstat = os.fstat

    def run_refresh(self):
        def root_fstat(fd):
            info = self.original_fstat(fd)
            return types.SimpleNamespace(st_mode=info.st_mode, st_uid=0,
                                         st_gid=0, st_nlink=info.st_nlink)
        with patch.object(refresh, "DEST", self.target), \
             patch.object(refresh.os, "geteuid", return_value=0), \
             patch.object(refresh.os, "fstat", side_effect=root_fstat), \
             patch.object(refresh, "mint", return_value={"expires_at": "2099-01-01T00:00:00Z"}) as minted, \
             patch.object(refresh, "write_token") as wrote:
            try:
                refresh.main()
            finally:
                self.minted_count = minted.call_count
                self.wrote_count = wrote.call_count

    def test_good_0700_real_directory_and_0600_lock(self):
        self.run_refresh()
        self.assertEqual(self.minted_count, len(refresh.ROLE_PERMISSIONS))
        self.assertEqual(self.wrote_count, len(refresh.ROLE_PERMISSIONS))
        lock = self.target / ".refresh.lock"
        self.assertTrue(lock.is_file())
        self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)

    def test_symlinked_token_dir_refused_without_chmod_target(self):
        victim = pathlib.Path(self.tmp.name) / "victim"
        victim.mkdir(mode=0o755)
        self.target.symlink_to(victim, target_is_directory=True)
        with self.assertRaises(OSError):
            self.run_refresh()
        self.assertEqual(stat.S_IMODE(victim.stat().st_mode), 0o755)
        self.assertEqual(self.minted_count, 0)

    def test_unsafe_directory_mode_refused(self):
        self.target.mkdir(mode=0o700)
        self.target.chmod(0o777)
        with self.assertRaisesRegex(RuntimeError, "Untrusted root-only"):
            self.run_refresh()
        self.assertEqual(self.minted_count, 0)

    def test_lock_symlink_refused(self):
        self.target.mkdir(mode=0o700)
        victim = pathlib.Path(self.tmp.name) / "victim-lock"
        victim.write_text("unchanged")
        (self.target / ".refresh.lock").symlink_to(victim)
        with self.assertRaises(OSError):
            self.run_refresh()
        self.assertEqual(victim.read_text(), "unchanged")
        self.assertEqual(self.minted_count, 0)

    def test_lock_mode_0644_refused(self):
        self.target.mkdir(mode=0o700)
        lock = self.target / ".refresh.lock"
        lock.write_text("existing")
        lock.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "Untrusted refresh lock"):
            self.run_refresh()
        self.assertEqual(self.minted_count, 0)


if __name__ == "__main__":
    unittest.main()
