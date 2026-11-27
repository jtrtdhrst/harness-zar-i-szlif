#!/usr/bin/env python3
"""Negative security regressions for root-only GitHub App token refresh paths.

No real provider calls, token reads, or persistent system paths are used.
Execute as a non-root test user. UID-0 ownership is simulated in fstat only.
"""
import importlib.util
import json
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


class ScopedWorkflowPermissionTests(unittest.TestCase):
    def test_only_scoped_implementer_and_release_roles_receive_workflows_write(self):
        allowed = {
            "implementer-harness", "implementer-product",
            "release-harness", "release-product",
        }
        for role in allowed:
            expected = dict(refresh.ROLE_PERMISSIONS[role.split("-", 1)[0]])
            expected["workflows"] = "write"
            self.assertEqual(refresh.ROLE_PERMISSIONS[role], expected)

        for role, permissions in refresh.ROLE_PERMISSIONS.items():
            if role not in allowed:
                with self.subTest(role=role):
                    self.assertNotIn("workflows", permissions)

    def test_mint_requests_only_the_exact_role_repository_and_permissions(self):
        for role, permissions in refresh.ROLE_PERMISSIONS.items():
            with self.subTest(role=role):
                repos = refresh.ROLE_REPOS.get(role, refresh.REPOS)
                names = refresh.ROLE_REPO_NAMES.get(role, refresh.REPO_NAMES)
                payload = {
                    "status": 201,
                    "app_id": refresh.APP_ID,
                    "installation_id": refresh.INSTALLATION_ID,
                    "token": "ghs_" + "x" * 50,
                    "expires_at": "2099-01-01T00:00:00Z",
                    "repositories": list(repos),
                    "permissions": permissions,
                }
                calls = []

                def fake_run(args, **kwargs):
                    calls.append(args[-1].split("--execute=", 1)[1])
                    return types.SimpleNamespace(
                        returncode=0, stdout=json.dumps(payload), stderr="")

                with patch.object(refresh.subprocess, "run", side_effect=fake_run):
                    grant = refresh.mint(role)

                self.assertEqual(grant["repositories"], list(repos))
                self.assertEqual(grant["permissions"], permissions)
                self.assertIn('"repositories"=>'+refresh.php_list(names), calls[0])
                self.assertIn('"permissions"=>'+refresh.php_map(permissions), calls[0])


class SafeRefreshPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent = pathlib.Path(self.tmp.name) / "etc-multica-git-credential"
        self.parent.mkdir(mode=0o700)
        self.target = self.parent / "roles"
        self.original_fstat = os.fstat

    def run_refresh(self, *, uid=0, gid=0, lock_uid=0, writer_enabled='false', writer_denied=False):
        def root_fstat(fd):
            info = self.original_fstat(fd)
            owner = lock_uid if stat.S_ISREG(info.st_mode) else uid
            return types.SimpleNamespace(st_mode=info.st_mode, st_uid=owner,
                                         st_gid=gid, st_nlink=info.st_nlink)
        def mint_role(role):
            if writer_denied and role == refresh.WRITER_ROLE:
                raise RuntimeError("GitHub App writer permission not granted")
            return {"expires_at": "2099-01-01T00:00:00Z"}
        with patch.dict(refresh.os.environ, {refresh.WRITER_OPT_IN: writer_enabled}), \
             patch.object(refresh, "DEST", self.target), \
             patch.object(refresh.os, "geteuid", return_value=0), \
             patch.object(refresh.os, "fstat", side_effect=root_fstat), \
             patch.object(refresh, "mint", side_effect=mint_role) as minted, \
             patch.object(refresh, "write_token") as wrote:
            try:
                refresh.main()
            finally:
                self.minted_count = minted.call_count
                self.wrote_count = wrote.call_count

    def test_good_0700_real_directory_and_0600_lock(self):
        self.run_refresh()
        self.assertEqual(self.minted_count, len(refresh.ROLE_PERMISSIONS) - 1)
        self.assertEqual(self.wrote_count, len(refresh.ROLE_PERMISSIONS) - 1)
        lock = self.target / ".refresh.lock"
        self.assertTrue(lock.is_file())
        self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)

    def test_writer_mint_requires_explicit_root_service_opt_in(self):
        self.run_refresh(writer_enabled='true')
        self.assertEqual(self.minted_count, len(refresh.ROLE_PERMISSIONS))
        self.assertEqual(self.wrote_count, len(refresh.ROLE_PERMISSIONS))

    def test_invalid_writer_gate_denied_before_any_token_issuance(self):
        with self.assertRaisesRegex(RuntimeError, "Invalid writer mint gate"):
            self.run_refresh(writer_enabled='yes')
        self.assertEqual(self.minted_count, 0)
        self.assertEqual(self.wrote_count, 0)

    def test_refused_optional_writer_grant_does_not_break_reader_rotation(self):
        self.run_refresh(writer_enabled='true', writer_denied=True)
        self.assertEqual(self.minted_count, len(refresh.ROLE_PERMISSIONS))
        self.assertEqual(self.wrote_count, len(refresh.ROLE_PERMISSIONS) - 1)

    def test_disabled_writer_revokes_stale_role_file(self):
        self.target.mkdir(mode=0o700)
        stale = self.target / 'github-ops-writer.json'
        stale.write_text('nonsecret-test-marker')
        stale.chmod(0o600)
        self.run_refresh(writer_enabled='false')
        self.assertFalse(stale.exists(), "opt-out must revoke the stale role file")
        self.assertEqual(self.minted_count, len(refresh.ROLE_PERMISSIONS) - 1)

    def test_disabled_writer_refuses_symlink_without_touching_target(self):
        self.target.mkdir(mode=0o700)
        victim = pathlib.Path(self.tmp.name) / 'victim-writer'
        victim.write_text('unchanged')
        (self.target / 'github-ops-writer.json').symlink_to(victim)
        with self.assertRaisesRegex(RuntimeError, "writer cleanup incomplete"):
            self.run_refresh(writer_enabled='false')
        self.assertEqual(victim.read_text(), 'unchanged')
        self.assertEqual(self.minted_count, 0)

    def test_symlinked_token_dir_refused_without_chmod_target(self):
        victim = pathlib.Path(self.tmp.name) / "victim"
        victim.mkdir(mode=0o755)
        victim.chmod(0o755)  # independent of CI/agent umask
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

    def test_nonroot_directory_uid_refused(self):
        self.target.mkdir(mode=0o700)
        with self.assertRaisesRegex(RuntimeError, "Untrusted root-only"):
            self.run_refresh(uid=997)
        self.assertEqual(self.minted_count, 0)

    def test_nonroot_directory_gid_refused(self):
        self.target.mkdir(mode=0o700)
        with self.assertRaisesRegex(RuntimeError, "Untrusted root-only"):
            self.run_refresh(gid=981)
        self.assertEqual(self.minted_count, 0)

    def test_nonroot_lock_owner_refused(self):
        self.target.mkdir(mode=0o700)
        with self.assertRaisesRegex(RuntimeError, "Untrusted refresh lock"):
            self.run_refresh(lock_uid=997)
        self.assertEqual(self.minted_count, 0)

    def test_lock_mode_0644_refused(self):
        self.target.mkdir(mode=0o700)
        lock = self.target / ".refresh.lock"
        lock.write_text("existing")
        lock.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "Untrusted refresh lock"):
            self.run_refresh()
        self.assertEqual(self.minted_count, 0)


class BghReaderOnlyTests(unittest.TestCase):
    def test_reader_only_projects_exact_grant_without_other_roles(self):
        from unittest.mock import Mock
        import runpy
        role = "github-ops-reader"
        permissions = refresh.ROLE_PERMISSIONS[role]
        repos = set(refresh.REPOS)
        directory = pathlib.Path("/fixture/bgh-volume")
        grant = {"role": role, "permissions": permissions,
                 "repositories": sorted(repos),
                 "expires_at": "2099-01-01T00:00:00Z"}
        volume = {"validated_volume": Mock(return_value=directory),
                  "project": Mock()}
        projector = {"check_dir": Mock(), "NODE_GID": 1000,
                     "PERMISSIONS": permissions, "REPOS": repos,
                     "SOURCE": "fixture-source", "TARGET": "fixture-target",
                     "project": Mock()}
        with patch.object(runpy, "run_path", side_effect=[volume, projector]), \
             patch.object(refresh, "mint", return_value=grant) as mint, \
             patch.object(refresh, "write_token") as write:
            self.assertEqual(refresh.refresh_bgh_reader(), 0)
        mint.assert_called_once_with(role)
        write.assert_called_once_with(role, grant)
        volume["project"].assert_called_once_with(grant, directory)
        projector["project"].assert_called_once_with(
            "fixture-source", "fixture-target", role, permissions)

    def test_invalid_volume_fails_before_issuing_any_grant(self):
        from unittest.mock import Mock
        import runpy
        volume = {"validated_volume": Mock(side_effect=RuntimeError("denied"))}
        with patch.object(runpy, "run_path", side_effect=[volume, {}]), \
             patch.object(refresh, "mint") as mint:
            with self.assertRaisesRegex(RuntimeError, "denied"):
                refresh.refresh_bgh_reader()
        mint.assert_not_called()

    def test_reader_mode_never_enters_legacy_role_loop(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = pathlib.Path(temp) / "root"
            parent.mkdir(mode=0o700)
            original = os.fstat
            def root_owned(fd):
                st = original(fd)
                return types.SimpleNamespace(st_mode=st.st_mode,
                    st_uid=0, st_gid=0, st_nlink=st.st_nlink)
            with patch.object(refresh, "DEST", parent / "roles"), \
                 patch.object(refresh.os, "geteuid", return_value=0), \
                 patch.object(refresh.os, "fstat", side_effect=root_owned), \
                 patch.object(refresh, "refresh_bgh_reader", return_value=0) as reader, \
                 patch.object(refresh, "selected_roles") as legacy, \
                 patch.object(refresh, "retire_writer_grant") as retire:
                self.assertEqual(refresh.main(reader_only=True), 0)
            reader.assert_called_once_with()
            legacy.assert_not_called()
            retire.assert_not_called()


if __name__ == "__main__":
    unittest.main()
