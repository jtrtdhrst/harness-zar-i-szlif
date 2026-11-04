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
            "servers": [{"name": "paperclip", "url": "https://mcp.example/mcp", "token": "opaque"}],
        }

    def test_valid_grant_builds_private_server_and_run_unique_scope(self):
        servers, scope = validate_grant(self.grant, authenticated_profile="cho", run_id="run-1", now=self.now)
        self.assertEqual(scope, "paperclip-run:cho:run-1")
        self.assertEqual(servers[0]["headers"][0]["value"], "Bearer opaque")

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


if __name__ == "__main__":
    unittest.main()
