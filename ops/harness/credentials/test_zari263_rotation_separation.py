#!/usr/bin/env python3
"""Deny unattended writer token rotation and cross-refresh credential races."""
import contextlib
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
SYSTEMD = HERE.parents[2] / "ops" / "systemd" / "github-ops-reader-refresh.service"


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


class ScheduledReaderIsolation(unittest.TestCase):
    def test_timer_is_truly_reader_only(self):
        unit = SYSTEMD.read_text()
        self.assertIn("ExecStart=/usr/bin/python3 /usr/local/libexec/"
                      "multica-zar-github-app-refresh.py --github-ops-reader-only", unit)
        self.assertNotIn("GITHUB_OPS_WRITER_MINT_ENABLED=true", unit)
        self.assertNotIn("ExecStartPost=", unit)
        self.assertNotIn("github-ops-token-project.py", unit)

    def test_refresh_disable_invokes_provider_first_cleanup_under_lock(self):
        refresh = load("multica-zar-github-app-refresh.py", "zari263_disable_lock")
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "credential-root"
            parent.mkdir(mode=0o700)
            roles = parent / "roles"
            original = os.fstat
            def trusted(fd):
                x = original(fd)
                return types.SimpleNamespace(st_mode=x.st_mode, st_uid=0, st_gid=0,
                                             st_nlink=x.st_nlink)
            visited = []
            def cleanup():
                visited.append("provider-and-all-copies")
            with patch.object(refresh, "DEST", roles), \
                 patch.object(refresh.os, "geteuid", return_value=0), \
                 patch.object(refresh.os, "fstat", side_effect=trusted), \
                 patch.object(refresh, "mint",
                              return_value={"expires_at": "2099-01-01T00:00:00Z"}), \
                 patch.object(refresh, "write_token"), \
                 patch.object(refresh, "cleanup_failed_writer", side_effect=cleanup), \
                 patch.dict(os.environ, {refresh.WRITER_OPT_IN: "false"}):
                self.assertEqual(refresh.main(), 0)
            self.assertEqual(visited, ["provider-and-all-copies"])

    def test_optional_writer_denial_triggers_provider_revoke(self):
        refresh = load("multica-zar-github-app-refresh.py", "zari263_denial_lock")
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "credential-root"
            parent.mkdir(mode=0o700)
            roles = parent / "roles"
            original = os.fstat
            def trusted(fd):
                x = original(fd)
                return types.SimpleNamespace(st_mode=x.st_mode, st_uid=0, st_gid=0,
                                             st_nlink=x.st_nlink)
            def mint(role):
                if role == refresh.WRITER_ROLE:
                    raise RuntimeError("synthetic permission refusal")
                return {"expires_at": "2099-01-01T00:00:00Z"}
            cleanup = Mock()
            with patch.object(refresh, "DEST", roles), \
                 patch.object(refresh.os, "geteuid", return_value=0), \
                 patch.object(refresh.os, "fstat", side_effect=trusted), \
                 patch.object(refresh, "mint", side_effect=mint), \
                 patch.object(refresh, "write_token"), \
                 patch.object(refresh, "cleanup_failed_writer", cleanup), \
                 patch.dict(os.environ, {refresh.WRITER_OPT_IN: "true"}):
                self.assertEqual(refresh.main(), 0)
            cleanup.assert_called_once_with()

    def test_provider_failure_does_not_report_successful_rotation(self):
        refresh = load("multica-zar-github-app-refresh.py", "zari263_denied_revoke")
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "credential-root"
            parent.mkdir(mode=0o700)
            roles = parent / "roles"
            original = os.fstat
            def trusted(fd):
                x = original(fd)
                return types.SimpleNamespace(st_mode=x.st_mode, st_uid=0, st_gid=0,
                                             st_nlink=x.st_nlink)
            failure = RuntimeError("synthetic provider revoke unavailable")
            with patch.object(refresh, "DEST", roles), \
                 patch.object(refresh.os, "geteuid", return_value=0), \
                 patch.object(refresh.os, "fstat", side_effect=trusted), \
                 patch.object(refresh, "mint") as mint, \
                 patch.object(refresh, "cleanup_failed_writer", side_effect=failure), \
                 patch.dict(os.environ, {refresh.WRITER_OPT_IN: "false"}):
                with self.assertRaisesRegex(RuntimeError, "synthetic provider"):
                    refresh.main()
            mint.assert_not_called()


class WriterLifecycleSerialization(unittest.TestCase):
    def test_projector_waits_for_refresh_lock_before_any_grant_read(self):
        project = load("github-ops-token-project.py", "zari263_flock")
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder) / "credential-root"
            base.mkdir(mode=0o700)
            role_dir = base / "roles"
            role_dir.mkdir(mode=0o700)
            original = os.fstat
            def root_stat(fd):
                x = original(fd)
                return types.SimpleNamespace(st_mode=x.st_mode, st_uid=0, st_gid=0,
                                             st_nlink=x.st_nlink)
            entered = threading.Event()
            release = threading.Event()
            arrived = threading.Event()
            order = []
            def owner():
                with project.writer_lifecycle_lock():
                    order.append("refresh_locked")
                    entered.set()
                    release.wait(3)
                    order.append("refresh_released")
            def projection():
                entered.wait(3)
                arrived.set()
                with project.writer_lifecycle_lock():
                    order.append("projection_locked")
            with patch.object(project, "WRITER_SOURCE", role_dir / "writer.json"), \
                 patch.object(project.os, "geteuid", return_value=0), \
                 patch.object(project.os, "fstat", side_effect=root_stat):
                a = threading.Thread(target=owner)
                b = threading.Thread(target=projection)
                a.start()
                self.assertTrue(entered.wait(3))
                b.start()
                self.assertTrue(arrived.wait(3))
                time.sleep(0.08)
                self.assertEqual(order, ["refresh_locked"],
                                 "projector must not read/rotate while refresh holds lock")
                release.set()
                a.join(3)
                b.join(3)
                self.assertFalse(a.is_alive())
                self.assertFalse(b.is_alive())
            self.assertEqual(order, ["refresh_locked", "refresh_released",
                                     "projection_locked"])


if __name__ == "__main__":
    unittest.main()
