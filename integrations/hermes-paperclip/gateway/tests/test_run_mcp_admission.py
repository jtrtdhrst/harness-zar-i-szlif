"""H02: exercise the *actual patched* Hermes /v1/runs admission boundary without a model."""
import asyncio
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import unittest
from gateway.platforms import api_server_runs


RUN = "00000000-0000-4000-8000-000000000151"
PROFILE = "cho"


class BeyondAdmission(Exception):
    pass


class FakeRequest:
    def __init__(self, grant, *, headers=None):
        self.headers = headers or {}
        self._grant = grant

    async def json(self):
        return {"input": "synthetic H02 admission", "paperclip_run_mcp": self._grant}


class Boundary:
    def __init__(self):
        self.normalized = False
        self.body = None

    def _parse_session_key_header(self, req):
        return "paperclip:run:" + RUN, None

    async def _normalize_room_dispatch(self, request, body):
        self.normalized = True
        self.body = body
        raise BeyondAdmission()


def grant():
    return {
        "version": 1, "company_id": "h02-company", "agent_id": "h02-agent",
        "issue_id": "KOMAA-1512", "run_id": RUN, "profile": PROFILE,
        "scopes": ["tools:call"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "servers": [{"name": "paperclip",
                     "url": "https://paperclip-mcp.zariszlif.pl/mcp",
                     "token": "h02-synthetic-grant"}],
    }


def headers():
    return {
        "X-Paperclip-Run-Id": RUN,
        "X-Hermes-Session-Key": "paperclip:run:" + RUN,
        "Idempotency-Key": RUN,
    }


class AdmissionTests(unittest.TestCase):
    def invoke(self, g, h, profile=PROFILE):
        from gateway.platforms import api_server
        server = Boundary()
        token = api_server._api_request_profile.set(profile)
        try:
            response = asyncio.run(api_server_runs._handle_runs(
                server, FakeRequest(g, headers=h), _api_server=api_server))
            return response, server
        finally:
            api_server._api_request_profile.reset(token)

    def test_valid_grant_enters_normal_run_admission_without_private_body(self):
        with self.assertRaises(BeyondAdmission):
            self.invoke(grant(), headers())

    def test_missing_or_wrong_run_headers_fail_closed(self):
        for missing in ("X-Paperclip-Run-Id", "Idempotency-Key", "X-Hermes-Session-Key"):
            h = headers()
            del h[missing]
            with self.subTest(missing=missing):
                response, boundary = self.invoke(grant(), h)
                self.assertEqual(response.status, 403)
                self.assertFalse(boundary.normalized)
        for key, bad in (("X-Paperclip-Run-Id", "00000000-0000-4000-8000-000000000152"),
                         ("Idempotency-Key", "another-idempotency-key"),
                         ("X-Hermes-Session-Key", "paperclip:run:foreign")):
            h = headers()
            h[key] = bad
            with self.subTest(key=key):
                response, boundary = self.invoke(grant(), h)
                self.assertEqual(response.status, 403)
                self.assertFalse(boundary.normalized)

    def test_foreign_profile_and_expired_grant_fail_closed(self):
        response, boundary = self.invoke(grant(), headers(), profile="cto")
        self.assertEqual(response.status, 403)
        self.assertFalse(boundary.normalized)
        expired = grant()
        expired["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        response, boundary = self.invoke(expired, headers())
        self.assertEqual(response.status, 403)
        self.assertFalse(boundary.normalized)

    def test_missing_grant_is_not_accepted(self):
        response, boundary = self.invoke(None, headers())
        self.assertEqual(response.status, 403)
        self.assertFalse(boundary.normalized)


if __name__ == "__main__":
    unittest.main()
