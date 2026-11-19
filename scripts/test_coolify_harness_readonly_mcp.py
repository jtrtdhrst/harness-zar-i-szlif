#!/usr/bin/env python3
"""Static fail-closed checks for the role-scoped Coolify MCP socket broker."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
UNIT = ROOT / "ops/systemd/coolify-harness-readonly-mcp.service"
WRAPPER = ROOT / "scripts/coolify-harness-readonly-mcp.sh"
SOCKET = "/srv/multica-zar/.hermes/profiles/harness-engineer/coolify-mcp-readonly.sock"

class ReadonlyBrokerContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.unit = UNIT.read_text(encoding="utf-8")
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")

    def test_pinned_role_and_socket(self):
        self.assertIn("User=multica-zar", self.unit)
        self.assertIn("Group=multica-zar", self.unit)
        self.assertIn("UNIX-LISTEN:" + SOCKET, self.unit)
        self.assertIn("mode=0600", self.unit)
        self.assertNotIn("TCP-LISTEN", self.unit)

    def test_credential_not_in_agent_or_commandline(self):
        self.assertIn("LoadCredential=coolify_readonly:/root/coolify-secrets/coolify_api_token_readonly", self.unit)
        self.assertIn('COOLIFY_ACCESS_TOKEN_FILE="$TOKEN_FILE"', self.wrapper)
        self.assertIn("unset COOLIFY_ACCESS_TOKEN", self.wrapper)
        self.assertNotIn("coolify_api_token\n", self.wrapper)
        self.assertNotIn("coolify_api_token_readonly", self.wrapper)

    def test_expected_process_protection(self):
        for x in ("NoNewPrivileges=yes", "ProtectSystem=strict", "PrivateTmp=yes",
                  "PrivateDevices=yes", "CapabilityBoundingSet="):
            self.assertIn(x, self.unit)

    def test_readonly_api_boundary(self):
        self.assertIn("COOLIFY_MCP_REQUIRE_HUMAN='on'", self.wrapper)
        self.assertIn("COOLIFY_BASE_URL='http://127.0.0.1:8001'", self.wrapper)
        self.assertNotIn("https://", self.wrapper)
        self.assertNotIn("COOLIFY_ACCESS_TOKEN=", self.wrapper)

    def test_npm_package_is_pinned(self):
        self.assertIn("/opt/multica-tools/coolify-harness-ro/node_modules/@masonator/coolify-mcp/dist/index.js", self.wrapper)
        self.assertIn("/usr/bin/node", self.wrapper)

    def test_wrapper_rejects_direct_agent_execution(self):
        self.assertIn('CREDENTIALS_DIRECTORY', self.wrapper)
        self.assertIn("MCP_SYSTEMD_CREDENTIAL_MISSING", self.wrapper)
        self.assertIn("MCP_RUN_USER_INVALID", self.wrapper)

if __name__ == "__main__":
    unittest.main(verbosity=2)
