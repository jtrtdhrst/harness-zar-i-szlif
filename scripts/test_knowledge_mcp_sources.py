#!/usr/bin/env python3
"""Offline structural regressions for the repo-owned knowledge MCP builds."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROLES = [
    "ceo", "cho", "cmo", "coo", "cpo", "cto", "designer", "email-creative",
    "engineer", "harness-engineer", "lifecycle-ops", "mascot-designer",
    "mcp-engineer", "ui-qa",
]

class KnowledgeMcpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.caddy = (ROOT / "hindsight-mcp/Caddyfile").read_text()
        cls.repowise = (ROOT / "repowise-mcp/Dockerfile").read_text()

    def test_exact_fourteen_banks_and_auth(self):
        for role in ROLES:
            symbol = role.replace("-", "_")
            env = role.upper().replace("-", "_")
            for matcher in (f"@mcp_{symbol}", f"@api_{symbol}"):
                self.assertIn(matcher, self.caddy)
            self.assertEqual(self.caddy.count(f'header Authorization "Bearer {{$HINDSIGHT_BANK_TOKEN_{env}}}"'), 2)
            self.assertIn(f"path /mcp/hermes-{role}/*", self.caddy)
            self.assertIn(f"/v1/default/banks/hermes-{role}/memories/recall", self.caddy)
        found = set(re.findall(r'@mcp_(\w+)\s*\{', self.caddy))
        self.assertEqual(found, {role.replace("-", "_") for role in ROLES})

    def test_deny_by_default(self):
        self.assertIn('respond "Not Found" 404', self.caddy)
        self.assertIn("header_up -X-Bank-Id", self.caddy)
        self.assertIn("header_up -Authorization", self.caddy)
        self.assertIn("method POST", self.caddy)

    def test_admin_scoped(self):
        self.assertIn("@vectorize_admin", self.caddy)
        self.assertIn('header Authorization "Bearer {$VECTORIZE_ADMIN_MCP_TOKEN}"', self.caddy)
        self.assertNotIn("header_up Authorization \"Bearer {$VECTORIZE_ADMIN_MCP_TOKEN}\"", self.caddy)

    def test_repowise_version_and_command(self):
        self.assertIn("ARG REPOWISE_VERSION=0.60.1", self.repowise)
        self.assertIn('ENTRYPOINT ["repowise", "mcp"]', self.repowise)
        self.assertIn('"streamable-http"', self.repowise)
        self.assertIn("USER repowise", self.repowise)

    def test_overrides_are_part_of_repowise_build(self):
        self.assertIn("COPY apply_overrides.py", self.repowise)
        self.assertIn("COPY overrides/", self.repowise)
        self.assertIn("RUN python /tmp/repowise-custom/apply_overrides.py", self.repowise)
        source = (ROOT / "repowise-mcp/apply_overrides.py").read_text()
        self.assertIn("Only .py overrides are allowed", source)
        self.assertIn("Target must be an existing RepoWise Python module", source)

    def test_no_inlined_tokens(self):
        for token_line in re.findall(r'Bearer ([^"\s]+)', self.caddy):
            self.assertTrue(token_line.startswith("{$"), token_line)

if __name__ == "__main__":
    unittest.main()
