"""Security contract for task-role provider admission (ZARI-213).

Runs offline: fake profiles, no OAuth, no provider requests, no service writes.
"""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
LAUNCHER = ROOT / "zari213-hermes-task-landlock.py"
spec = importlib.util.spec_from_file_location("zari213_landlock_policy_tested", LAUNCHER)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

ROLES = ("ceo", "cho", "cmo", "coo", "cpo", "cto", "designer",
         "email-creative", "engineer", "harness-engineer", "lifecycle-ops",
         "mascot-designer", "mcp-engineer", "ui-qa")


class RoleProviderIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / "profiles").mkdir()

    def add_profile(self, role, provider="opencode-go"):
        directory = self.home / "profiles" / role
        directory.mkdir()
        config = directory / "config.yaml"
        config.write_text("model:\n  provider: " + provider + "\n", encoding="utf-8")
        config.chmod(0o600)
        env = directory / ".env"
        env.write_text("DUMMY_NONSECRET=1\n", encoding="utf-8")
        env.chmod(0o600)
        return directory

    def test_only_the_fourteen_scoped_opencode_roles_are_authorized(self):
        self.assertEqual(policy.CODEX_ROLES, frozenset())
        self.assertEqual(policy.OPENCODE_ROLES, frozenset(ROLES))
        for role in ROLES:
            with self.subTest(role=role):
                self.add_profile(role)
                self.assertEqual(policy.role_model_provider(self.home, role, os.getuid()), "opencode-go")
                self.assertEqual(policy.private_role_env_file(self.home, role, os.getuid()),
                                 self.home / "profiles" / role / ".env")

    def test_codex_provider_is_denied_for_every_role(self):
        for role in ROLES:
            with self.subTest(role=role):
                self.add_profile(role, "openai-codex")
                with self.assertRaisesRegex(ValueError, "not approved"):
                    policy.role_model_provider(self.home, role, os.getuid())

    def test_unknown_role_cannot_select_provider(self):
        self.add_profile("unknown-role")
        with self.assertRaisesRegex(ValueError, "no model credential policy"):
            policy.role_model_provider(self.home, "unknown-role", os.getuid())

    def test_symlink_and_permissive_provider_files_are_denied(self):
        profile = self.add_profile("cho")
        config = profile / "config.yaml"
        config.unlink()
        config.symlink_to(profile / ".env")
        with self.assertRaises(OSError):
            policy.role_model_provider(self.home, "cho", os.getuid())
        config.unlink()
        config.write_text("model:\n  provider: opencode-go\n")
        config.chmod(0o600)
        (profile / ".env").chmod(0o644)
        with self.assertRaisesRegex(ValueError, "not private"):
            policy.private_role_env_file(self.home, "cho", os.getuid())

    def test_no_shared_oauth_grant_in_launch_path(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertNotIn('grant(ruleset, shared_home / "auth.json", READ_FILE)', source)
        self.assertIn("private_role_env_file(shared_home, role, os.getuid())", source)


if __name__ == "__main__":
    unittest.main()
