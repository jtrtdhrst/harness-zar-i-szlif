import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_mcp import InvalidRunGrant, validate_grant


class RunMcpGrantTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 4, tzinfo=timezone.utc)
        self.grant = {
            "version": 1, "company_id": "company-1", "agent_id": "agent-1",
            "issue_id": "KOMAA-1512", "run_id": "run-1", "profile": "cho",
            "scopes": ["tools:call"], "expires_at": "2026-11-04T00:01:00Z",
            "servers": [{"name": "paperclip", "url": "https://paperclip-mcp.zariszlif.pl/mcp", "token": "opaque"}],
        }

    def test_valid_grant_builds_private_server_and_run_unique_scope(self):
        servers, scope = validate_grant(self.grant, authenticated_profile="cho", run_id="run-1", now=self.now)
        self.assertEqual(scope, "paperclip-run:cho:run-1")
        self.assertEqual(servers[0]["headers"][0]["value"], "Bearer opaque")
        self.assertIs(servers[0]["strict_redirect_headers"], True)

    def test_wrong_run_and_profile_are_rejected(self):
        for profile, run in (("cho", "run-2"), ("cto", "run-1")):
            with self.subTest(profile=profile, run=run), self.assertRaises(InvalidRunGrant):
                validate_grant(self.grant, authenticated_profile=profile, run_id=run, now=self.now)

    def test_expired_and_escalated_scopes_are_rejected(self):
        expired = {**self.grant, "expires_at": "2026-11-03T23:59:00Z"}
        elevated = {**self.grant, "scopes": ["tools:call", "wiki:write"]}
        for grant in (expired, elevated):
            with self.subTest(grant=grant), self.assertRaises(InvalidRunGrant):
                validate_grant(grant, authenticated_profile="cho", run_id="run-1", now=self.now)

    def test_unknown_fields_and_plaintext_http_are_rejected(self):
        for grant in ({**self.grant, "extra": "ignored?"},
                      {**self.grant, "servers": [{"name": "paperclip", "url": "http://mcp", "token": "opaque"}]}):
            with self.subTest(grant=grant), self.assertRaises(InvalidRunGrant):
                validate_grant(grant, authenticated_profile="cho", run_id="run-1", now=self.now)


    def test_bearer_must_not_be_forwarded_to_unknown_https_origins(self):
        base = "https://paperclip-mcp.zariszlif.pl/mcp"
        rejected = (
            "https://evil.example/mcp",
            "https://paperclip-mcp.zariszlif.pl.evil.example/mcp",
            "https://operator@paperclip-mcp.zariszlif.pl/mcp",
            "https://paperclip-mcp.zariszlif.pl:8443/mcp",
            base + "?forward=evil",
            base + "#fragment",
            "https://127.0.0.1/mcp",
            "https://localhost/mcp",
            "https://paperclip-mcp.zariszlif.pl/other",
            base + "/..",
        )
        for url in rejected:
            grant = {**self.grant, "servers": [
                {"name": "paperclip", "url": url, "token": "opaque"}
            ]}
            with self.subTest(url=url), self.assertRaises(InvalidRunGrant):
                validate_grant(grant, authenticated_profile="cho",
                               run_id="run-1", now=self.now)

    def test_paperclip_native_issuer_run_gateway_and_core_tool_endpoints(self):
        """Only Paperclip's exact host and server-minted gateway IDs are admitted."""
        urls = (
            "https://paperclip.kompaszbiorek.pl/mcp/gateways/gw_" + "a" * 32,
            "https://paperclip.kompaszbiorek.pl/api/mcp/project-tools",
            "https://paperclip.kompaszbiorek.pl/mcp/runtime-tools",
        )
        for url in urls:
            with self.subTest(url=url):
                grant = {**self.grant, "servers": [{"name": "paperclip", "url": url, "token": "opaque"}]}
                specs, scope = validate_grant(grant, authenticated_profile="cho", run_id="run-1", now=self.now)
                self.assertEqual(specs[0]["url"], url)
                self.assertTrue(specs[0]["strict_redirect_headers"])
                self.assertEqual(scope, "paperclip-run:cho:run-1")

    def test_native_issuer_urls_deny_cross_origin_redirect_and_path_variants(self):
        base = "https://paperclip.kompaszbiorek.pl"
        gateway = base + "/mcp/gateways/gw_" + "a" * 32
        rejected = (
            gateway + "?to=evil", gateway + "#ignore", gateway + "/..",
            base + "/mcp/gateways/gw_" + "z" * 32,
            base + "/mcp/gateways/gw_" + "a" * 31,
            base + "/mcp/gateways/../gw_" + "a" * 32,
            base + "/mcp/gateways/gw_%61" + "a" * 31,
            base + "/api/mcp/project-tools/../secrets",
            base + "/api/mcp/project-tools/",
            base + "/mcp/gateway", base + "/api/secrets", base + "/mcp",
            "https://paperclip.kompaszbiorek.pl.evil.example/mcp/gateways/gw_" + "a" * 32,
            "https://attacker@paperclip.kompaszbiorek.pl/mcp/gateways/gw_" + "a" * 32,
            "https://paperclip.kompaszbiorek.pl:8443/mcp/gateways/gw_" + "a" * 32,
            "http://paperclip.kompaszbiorek.pl/mcp/gateways/gw_" + "a" * 32,
        )
        for url in rejected:
            with self.subTest(url=url), self.assertRaises(InvalidRunGrant):
                validate_grant({**self.grant, "servers": [
                    {"name": "paperclip", "url": url, "token": "opaque"}
                ]}, authenticated_profile="cho", run_id="run-1", now=self.now)

    def test_operator_kill_switch_blocks_native_core_urls_too(self):
        import os
        from unittest.mock import patch
        native = {**self.grant, "servers": [{
            "name": "paperclip", "url": "https://paperclip.kompaszbiorek.pl/mcp/gateways/gw_" + "a" * 32,
            "token": "opaque",
        }]}
        with patch.dict(os.environ, {"HERMES_PAPERCLIP_MCP_URLS": ""}):
            with self.assertRaises(InvalidRunGrant):
                validate_grant(native, authenticated_profile="cho", run_id="run-1", now=self.now)

    def test_bearer_header_injection_and_whitespace_are_rejected(self):
        for bearer in ("token" + chr(13) + chr(10) + "X-Forged: yes", "token value", "token" + chr(9) + "value", "sketch" + chr(10)):
            grant = {**self.grant, "servers": [
                {"name": "paperclip",
                 "url": "https://paperclip-mcp.zariszlif.pl/mcp", "token": bearer}
            ]}
            with self.subTest(bearer=repr(bearer)), self.assertRaises(InvalidRunGrant):
                validate_grant(grant, authenticated_profile="cho",
                               run_id="run-1", now=self.now)

    def test_fixed_rejection_codes_never_log_tokens_or_external_urls(self):
        from unittest.mock import patch
        invalid = {**self.grant, "servers": [
            {"name": "paperclip", "url": "https://evil.example/mcp?private=neverlog",
             "token": "opaque-very-secret-marker"}
        ]}
        with self.assertLogs("gateway.run_mcp", level="WARNING") as logs:
            with self.assertRaisesRegex(InvalidRunGrant, "^invalid run MCP grant$"):
                validate_grant(invalid, authenticated_profile="cho", run_id="run-1", now=self.now)
        events = " ".join(logs.output)
        self.assertIn("run_mcp_denied reason=server_url", events)
        self.assertNotIn("secret-marker", events)
        self.assertNotIn("evil.example", events)
        self.assertNotIn("neverlog", events)

    def test_rejection_categories_preserve_existing_denial_contract(self):
        from unittest.mock import patch
        tests = (
            ({**self.grant, "profile": "cto"}, "profile_mismatch"),
            ({**self.grant, "scopes": ["wiki:write"]}, "scopes"),
            ({**self.grant, "expires_at": "2026-11-03T10:00:00Z"}, "expiry"),
        )
        for bad, reason in tests:
            with self.subTest(reason=reason):
                with self.assertLogs("gateway.run_mcp", level="WARNING") as logs:
                    with self.assertRaisesRegex(InvalidRunGrant, "^invalid run MCP grant$"):
                        validate_grant(bad, authenticated_profile="cho", run_id="run-1", now=self.now)
                self.assertIn("run_mcp_denied reason=" + reason, " ".join(logs.output))

    def test_operator_can_disable_all_external_run_mcp_destinations(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"HERMES_PAPERCLIP_MCP_URLS": ""}):
            with self.assertRaises(InvalidRunGrant):
                validate_grant(self.grant, authenticated_profile="cho",
                               run_id="run-1", now=self.now)


if __name__ == "__main__":
    unittest.main()
