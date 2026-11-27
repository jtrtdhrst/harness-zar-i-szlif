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

    def test_zari315_github_ops_readers_have_minimum_pr_provenance_scope(self):
        refresh = load("multica-zar-github-app-refresh.py", "zari315_refresh")
        legacy = load("github-ops-token-project.py", "zari315_reader_project")
        image = load("github-ops-image-reader-project.py", "zari315_image_project")
        expected = {
            "actions": "read",
            "administration": "read",
            "contents": "read",
            "deployments": "read",
            "pull_requests": "read",
            "metadata": "read",
        }
        for grant in (
            refresh.ROLE_PERMISSIONS["github-ops-reader"],
            refresh.ROLE_PERMISSIONS["github-ops-reader-image"],
            legacy.PERMISSIONS,
            image.PERMISSIONS,
        ):
            with self.subTest(grant=grant):
                self.assertEqual(grant, expected)
                self.assertNotIn("write", grant.values())
                self.assertNotIn("issues", grant)
        self.assertEqual(refresh.ROLE_PERMISSIONS["github-ops-writer"]["pull_requests"], "write")
        self.assertNotEqual(refresh.ROLE_PERMISSIONS["github-ops-reader"], refresh.ROLE_PERMISSIONS["github-ops-writer"])

    def test_timer_is_truly_reader_only(self):
        unit = SYSTEMD.read_text()
        self.assertIn("ExecStart=/usr/bin/python3 /usr/local/libexec/"
                      "multica-zar-github-app-refresh.py --github-ops-reader-only", unit)
        self.assertIn("Environment=GITHUB_OPS_IMAGE_APP_UUID="
                      "sf67p2qio3qf31dwvkp5gcfw", unit)
        self.assertIn("Environment=GITHUB_OPS_IMAGE_READER_VOLUME="
                      "sf67p2qio3qf31dwvkp5gcfw-sf67p2qio3qf31dwvkp5gcfw-"
                      "github-ops-image-reader", unit)
        self.assertNotIn("GITHUB_OPS_WRITER_MINT_ENABLED=true", unit)
        self.assertNotIn("ExecStartPost=", unit)
        self.assertNotIn("github-ops-token-project.py", unit)

    def test_reader_only_rotates_both_scoped_readers_under_refresh_lock(self):
        import runpy

        refresh = load("multica-zar-github-app-refresh.py", "zari263_dual_reader")
        image_project = Mock()
        legacy_project = Mock()
        legacy = {
            "check_dir": Mock(), "NODE_GID": 1000,
            "SOURCE": Path("/root/roles/github-ops-reader.json"),
            "TARGET": Path("/runtime/reader/token.json"),
            "PERMISSIONS": refresh.ROLE_PERMISSIONS["github-ops-reader"],
            "REPOS": set(refresh.REPOS), "project": legacy_project,
        }
        image = {
            "PERMISSIONS": refresh.ROLE_PERMISSIONS[refresh.IMAGE_READER_ROLE],
            "REPOS": list(refresh.REPOS),
            "validated_volume": Mock(
                side_effect=lambda app, name: Path("/volume") / app / name),
        }
        lock_state = {"held": False}
        original_flock = fcntl.flock

        def tracked_flock(fd, operation):
            if operation == fcntl.LOCK_EX:
                lock_state["held"] = True
            return original_flock(fd, operation)

        expiry = "2099-01-01T00:00:00Z"

        def grant(role):
            self.assertTrue(lock_state["held"], "reader grant minted outside refresh lock")
            return {"role": role,
                    "permissions": refresh.ROLE_PERMISSIONS[role],
                    "repositories": sorted(refresh.ROLE_REPOS.get(role, refresh.REPOS)),
                    "expires_at": expiry,
                    "token": "t" * 50}

        def project_image(grant_data, directory):
            self.assertTrue(lock_state["held"], "reader token projected outside refresh lock")
            image_project(grant_data, directory)

        image["project"] = project_image

        with tempfile.TemporaryDirectory() as folder:
            roles = Path(folder) / "roles"
            original_fstat = os.fstat

            def trusted(fd):
                info = original_fstat(fd)
                return types.SimpleNamespace(st_mode=info.st_mode, st_uid=0,
                                             st_gid=0, st_nlink=info.st_nlink)

            with patch.object(refresh, "DEST", roles), \
                 patch.object(refresh.os, "geteuid", return_value=0), \
                 patch.object(refresh.os, "fstat", side_effect=trusted), \
                 patch.object(refresh.fcntl, "flock", side_effect=tracked_flock), \
                 patch.object(runpy, "run_path", side_effect=[image, legacy]), \
                 patch.object(refresh, "mint", side_effect=grant) as mint, \
                 patch.object(refresh, "write_token") as write_token, \
                 patch.dict(os.environ, {
                     "GITHUB_OPS_IMAGE_APP_UUID": refresh.IMAGE_READER_APP_UUID,
                     "GITHUB_OPS_IMAGE_READER_VOLUME": refresh.IMAGE_READER_VOLUME,
                     refresh.WRITER_OPT_IN: "false",
                 }):
                self.assertEqual(refresh.main(reader_only=True), 0)

        self.assertEqual([call.args[0] for call in mint.call_args_list],
                         ["github-ops-reader", refresh.IMAGE_READER_ROLE])
        self.assertEqual([call.args[0] for call in write_token.call_args_list],
                         ["github-ops-reader", refresh.IMAGE_READER_ROLE])
        image["validated_volume"].assert_any_call(
            refresh.IMAGE_READER_APP_UUID, refresh.IMAGE_READER_VOLUME)
        self.assertEqual(
            [call.args[0]["role"] for call in image_project.call_args_list],
            ["github-ops-reader", refresh.IMAGE_READER_ROLE])
        legacy_project.assert_called_once()

    def test_reader_only_rejects_bad_image_mapping_before_any_mint(self):
        refresh = load("multica-zar-github-app-refresh.py", "zari263_bad_image_mapping")
        mappings = (
            ("", ""),
            ("a" * 24, refresh.IMAGE_READER_VOLUME),
            (refresh.IMAGE_READER_APP_UUID, "wrong-volume"),
        )
        for app_uuid, volume in mappings:
            with self.subTest(app_uuid=app_uuid, volume=volume), \
                 patch.object(refresh, "mint") as mint, \
                 patch.dict(os.environ, {
                     "GITHUB_OPS_IMAGE_APP_UUID": app_uuid,
                     "GITHUB_OPS_IMAGE_READER_VOLUME": volume,
                 }):
                with self.assertRaisesRegex(RuntimeError, "mapping mismatch"):
                    refresh.refresh_bgh_reader()
                mint.assert_not_called()

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
