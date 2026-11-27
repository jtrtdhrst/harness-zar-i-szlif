#!/usr/bin/env python3
"""Deny unattended writer token rotation and cross-refresh credential races."""
import contextlib
import fcntl
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import threading
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
    def test_actual_minter_and_projector_share_lock_without_sleep(self):
        # This test deliberately invokes refresh._refresh_core(), not
        # projector.writer_lifecycle_lock() twice. Projector readiness is
        # signalled just BEFORE its LOCK_EX syscall; no scheduler sleep.
        refresh = load("multica-zar-github-app-refresh.py", "zari263_real_minter_lock")
        project = load("github-ops-token-project.py", "zari263_projector_real_lock")
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder) / "credential-root"
            base.mkdir(mode=0o700)
            role_dir = base / "roles"
            role_dir.mkdir(mode=0o700)
            original_fstat = os.fstat
            original_flock = fcntl.flock
            def root_stat(fd):
                st = original_fstat(fd)
                return types.SimpleNamespace(st_mode=st.st_mode, st_uid=0,
                                             st_gid=0, st_nlink=st.st_nlink)
            mint_held = threading.Event()
            release_minter = threading.Event()
            projector_attempted = threading.Event()
            projector_executed = threading.Event()
            order, errors = [], []

            def mint_under_real_refresh_lock(role):
                order.append("mint_enter")
                mint_held.set()
                if not release_minter.wait(5):
                    raise RuntimeError("test timed out waiting to unlock minter")
                order.append("mint_release")
                return {"expires_at":"2099-01-01T00:00:00Z"}

            def spy_lock(fd, operation):
                if (threading.current_thread().name == "zari263-projector"
                        and operation == fcntl.LOCK_EX):
                    projector_attempted.set()
                return original_flock(fd, operation)

            def projection_entry():
                order.append("projection_enter")
                projector_executed.set()

            def run_minter():
                try:
                    refresh._refresh_core(reader_only=False)
                except Exception as exc:
                    errors.append(("minter", type(exc).__name__))

            def run_projector():
                try:
                    project.main()
                except Exception as exc:
                    errors.append(("projector", type(exc).__name__))

            with patch.object(refresh, "DEST", role_dir), \
                 patch.object(project, "WRITER_SOURCE", role_dir / "writer.json"), \
                 patch.object(refresh.os, "geteuid", return_value=0), \
                 patch.object(refresh.os, "fstat", side_effect=root_stat), \
                 patch.object(project.fcntl, "flock", side_effect=spy_lock), \
                 patch.object(refresh, "selected_roles", return_value=["github-ops-reader"]), \
                 patch.object(refresh, "mint", side_effect=mint_under_real_refresh_lock), \
                 patch.object(refresh, "write_token"), \
                 patch.object(refresh, "cleanup_failed_writer"), \
                 patch.object(project, "_project_once", side_effect=projection_entry), \
                 patch.dict(os.environ, {"GITHUB_OPS_IMAGE_APP_UUID": "",
                                        "GITHUB_OPS_IMAGE_READER_VOLUME": ""}):
                minter = threading.Thread(target=run_minter, name="zari263-minter")
                projector = threading.Thread(target=run_projector, name="zari263-projector")
                try:
                    minter.start()
                    self.assertTrue(mint_held.wait(3), "minter never acquired lock")
                    projector.start()
                    self.assertTrue(projector_attempted.wait(3),
                                    "projector did not attempt real flock")
                    self.assertFalse(projector_executed.is_set(),
                                     "projector escaped minter lock")
                finally:
                    release_minter.set()
                    minter.join(5)
                    if projector.ident is not None:
                        projector.join(5)
                self.assertFalse(minter.is_alive())
                self.assertFalse(projector.is_alive())
            self.assertFalse(errors, errors)
            self.assertEqual(order, ["mint_enter", "mint_release", "projection_enter"])


if __name__ == "__main__":
    unittest.main()
