"""No-real-secret regression suite for per-role Hermes model env projection."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from role_env_projector import project, ROLE_PROVIDER, MARKER


class RoleProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.key = "DEMO_ONLY_KEY_0123456789"
        (self.root / ".env").write_text("OPENCODE_GO_API_KEY=" + self.key + "\n")
        (self.root / ".env").chmod(0o600)
        for role, provider in ROLE_PROVIDER.items():
            role_dir = self.root / "profiles" / role
            role_dir.mkdir(parents=True)
            role_dir.chmod(0o700)
            (role_dir / "config.yaml").write_text("model:\n  provider: " + provider + "\n")
            (role_dir / ".env").symlink_to(self.root / ".env")
        self.uid, self.gid = os.getuid(), os.getgid()

    def call(self, apply=False):
        return project(self.root, uid=self.uid, gid=self.gid, apply=apply)

    def test_root_invocation_refused_without_any_mutation(self):
        source_before = (self.root / ".env").read_bytes()
        with mock.patch("role_env_projector.os.geteuid", return_value=0):
            with self.assertRaisesRegex(PermissionError, "root execution refused"):
                self.call(apply=True)
        self.assertEqual((self.root / ".env").read_bytes(), source_before)
        for role in ROLE_PROVIDER:
            self.assertTrue((self.root / "profiles" / role / ".env").is_symlink())

    def test_wrong_nonroot_identity_refused(self):
        with mock.patch("role_env_projector.os.geteuid", return_value=self.uid + 1000):
            with self.assertRaisesRegex(PermissionError, "does not own"):
                self.call(apply=True)
        self.assertTrue((self.root / "profiles" / "cho" / ".env").is_symlink())

    def test_exact_role_provider_projection(self):
        self.assertEqual(self.call()["changes_needed"], len(ROLE_PROVIDER))
        self.assertEqual(self.call(apply=True)["changed"], len(ROLE_PROVIDER))
        for role, provider in ROLE_PROVIDER.items():
            p = self.root / "profiles" / role / ".env"
            self.assertFalse(p.is_symlink())
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            data = p.read_text()
            self.assertTrue(data.startswith(MARKER))
            if provider == "openai-codex":
                self.assertNotIn("OPENCODE_GO_API_KEY=", data)
                self.assertNotIn(self.key, data)
            else:
                self.assertIn("OPENCODE_GO_API_KEY="+self.key, data)
        self.assertEqual(self.call(apply=True)["changed"], 0)
        self.assertEqual((self.root / ".env").read_text(),
                         "OPENCODE_GO_API_KEY="+self.key+"\n")

    def test_missing_or_extra_source_variable_refused_before_mutation(self):
        (self.root / ".env").write_text(
            "OPENCODE_GO_API_KEY="+self.key+"\nUNEXPECTED_PROVIDER_SECRET=TEST\n")
        with self.assertRaisesRegex(RuntimeError, "schema drift"):
            self.call(apply=True)
        self.assertTrue((self.root/"profiles"/"cho"/".env").is_symlink())

    def test_role_provider_drift_refused(self):
        (self.root / "profiles" / "cto" / "config.yaml").write_text(
            "model:\n  provider: openai-codex\n")
        with self.assertRaisesRegex(RuntimeError, "provider drift"):
            self.call(apply=True)
        self.assertTrue((self.root/"profiles"/"cho"/".env").is_symlink())

    def test_arbitrary_symlink_target_refused(self):
        p=self.root / "profiles" / "cho" / ".env"
        p.unlink()
        p.symlink_to(self.root / "profiles" / "cto" / "config.yaml")
        with self.assertRaisesRegex(RuntimeError, "unexpected role"):
            self.call(apply=True)

    def test_unmanaged_regular_file_refused(self):
        p=self.root / "profiles" / "cho" / ".env"
        p.unlink()
        p.write_text("UNRELATED_CONFIG=do-not-overwrite\n")
        p.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, "unmanaged"):
            self.call(apply=True)
        self.assertEqual(p.read_text(), "UNRELATED_CONFIG=do-not-overwrite\n")


if __name__ == "__main__":
    unittest.main()
