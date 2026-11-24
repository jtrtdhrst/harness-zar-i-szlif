"""Role broker policy parser and cross-role denial tests."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).with_name("zari213-hermes-task-landlock.py")
spec = importlib.util.spec_from_file_location("zari213_landlock_policy", SOURCE)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class RoleBrokerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / "profiles" / "cho").mkdir(parents=True, mode=0o700)
        self.config = self.home / "profiles" / "cho" / "config.yaml"
        self.uid = os.getuid()

    def write_config(self, url="http://127.0.0.1:7468/p/cho/v1",
                     provider="custom:rolebroker"):
        self.config.write_text(
            "model:\n"
            f"  provider: {provider}\n"
            "  default: gpt-6-luna\n"
            "providers:\n"
            "  rolebroker:\n"
            "    name: rolebroker\n"
            f"    base_url: {url}\n"
            "    key_env: ROLE_BROKER_API_KEY\n"
            "    api_mode: codex_responses\n"
            "    default_model: gpt-6-luna\n"
        )
        self.config.chmod(0o600)

    def test_role_bound_broker_provider_allowed(self):
        self.write_config()
        self.assertEqual(policy.role_model_provider(self.home, "cho", self.uid),
                         "custom:rolebroker")

    def test_foreign_role_route_denied(self):
        self.write_config(url="http://127.0.0.1:7468/p/cto/v1")
        with self.assertRaisesRegex(ValueError, "not pinned to this role"):
            policy.role_model_provider(self.home, "cho", self.uid)

    def test_shared_codex_oauth_provider_denied(self):
        self.write_config(provider="openai-codex")
        with self.assertRaisesRegex(ValueError, "not approved"):
            policy.role_model_provider(self.home, "cho", self.uid)

    def test_wrong_broker_key_env_denied(self):
        self.write_config()
        text = self.config.read_text().replace(
            "ROLE_BROKER_API_KEY", "OPENCODE_GO_API_KEY")
        self.config.write_text(text)
        self.config.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "not pinned to this role"):
            policy.role_model_provider(self.home, "cho", self.uid)


if __name__ == "__main__":
    unittest.main()
