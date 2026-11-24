"""No-real-secret regression tests for role-scoped Hermes broker projection."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from role_env_projector import MARKER, ROLE_PROVIDER, project


class RoleProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "hermes"
        self.keys = base / "keys"
        self.profiles = self.root / "profiles"
        self.profiles.mkdir(parents=True)
        self.keys.mkdir()
        self.uid, self.gid = (os.getuid() or 997), (os.getgid() or 997)
        for item in [self.root, *self.root.rglob("*"), self.keys, *self.keys.rglob("*")]:
            os.chown(item, self.uid, self.gid)
        self.role_keys = {}
        for index, role in enumerate(ROLE_PROVIDER):
            profile = self.profiles / role
            profile.mkdir(mode=0o700)
            profile.chmod(0o700)
            config = (
                "_config_version: 1\n"
                "model:\n"
                "  provider: openai-codex\n"
                "  default: gpt-6-luna\n"
                "mcp_servers: {}\n"
                "terminal:\n"
                "  backend: local\n"
            )
            (profile / "config.yaml").write_text(config)
            (profile / "config.yaml").chmod(0o600)
            (profile / ".env").symlink_to(self.root / ".env")
            keydir = self.keys / role
            keydir.mkdir(mode=0o700)
            keydir.chmod(0o700)
            key = f"TEST_ROLE_KEY_{index:03d}_" + ("a" * 40)
            self.role_keys[role] = key
            (keydir / "api-key").write_text(key + "\n")
            (keydir / "api-key").chmod(0o600)
        (self.root / ".env").write_text("GLOBAL_DECOY_MUST_NOT_BE_READ\n")
        (self.root / ".env").chmod(0o600)

    def call_project(self, apply=False):
        with mock.patch("role_env_projector.os.geteuid", return_value=self.uid):
            return project(self.root, key_root=self.keys, uid=self.uid, gid=self.gid, apply=apply)

    def test_root_invocation_refused_without_mutation(self):
        before = (self.profiles / "cho" / "config.yaml").read_bytes()
        with mock.patch("role_env_projector.os.geteuid", return_value=0):
            with self.assertRaisesRegex(PermissionError, "root execution refused"):
                project(self.root, key_root=self.keys, uid=self.uid, gid=self.gid, apply=True)
        self.assertEqual((self.profiles / "cho" / "config.yaml").read_bytes(), before)
        self.assertTrue((self.profiles / "cho" / ".env").is_symlink())

    def test_role_bound_config_and_distinct_private_keys(self):
        self.assertEqual(self.call_project()["changes_needed"], len(ROLE_PROVIDER))
        result = self.call_project(apply=True)
        self.assertEqual(result["changed"], len(ROLE_PROVIDER))
        for role in ROLE_PROVIDER:
            profile = self.profiles / role
            config = (profile / "config.yaml").read_text()
            self.assertIn("  provider: custom:rolebroker\n", config)
            self.assertIn(f"    base_url: http://127.0.0.1:7468/p/{role}/v1\n", config)
            self.assertIn("    key_env: ROLE_BROKER_API_KEY\n", config)
            self.assertIn("    api_mode: codex_responses\n", config)
            env = profile / ".env"
            self.assertFalse(env.is_symlink())
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)
            data = env.read_text()
            self.assertTrue(data.startswith(MARKER + "\n"))
            self.assertIn("ROLE_BROKER_API_KEY=" + self.role_keys[role] + "\n", data)
            self.assertNotIn("GLOBAL_DECOY", data)
            for other, key in self.role_keys.items():
                if other != role:
                    self.assertNotIn(key, data)
        self.assertEqual(self.call_project(apply=True)["changed"], 0)

    def test_unexpected_provider_block_refused(self):
        path = self.profiles / "cho" / "config.yaml"
        path.write_text(path.read_text() + "providers:\n  other:\n    api_mode: openai\n")
        path.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, "unmanaged Hermes providers"):
            self.call_project(apply=True)
        self.assertTrue((self.profiles / "cho" / ".env").is_symlink())

    def test_symlink_role_key_refused(self):
        key = self.keys / "cto" / "api-key"
        key.unlink()
        key.symlink_to(self.keys / "cho" / "api-key")
        with self.assertRaises(OSError):
            self.call_project(apply=True)
        self.assertTrue((self.profiles / "cho" / ".env").is_symlink())

    def test_foreign_role_env_symlink_refused(self):
        env = self.profiles / "cto" / ".env"
        env.unlink()
        env.symlink_to(self.profiles / "cho" / "config.yaml")
        with self.assertRaisesRegex(RuntimeError, "unexpected role .env symlink"):
            self.call_project(apply=True)
        self.assertTrue((self.profiles / "cho" / ".env").is_symlink())


if __name__ == "__main__":
    unittest.main()
