"""Explicit positive/negative role and data-plane tests for the trusted Codex broker."""
import json
import tempfile
import unittest
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer
from codex_role_broker import create_app, role_secret, UPSTREAM

CHO = "c" * 50
COO = "o" * 50

class FakeStream:
    async def iter_chunked(self, n):
        yield b'data: {"type":"response.completed"}\n\n'

class Upstream:
    status = 200
    content = FakeStream()
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False

class Session:
    def __init__(self, owner, **kwargs): self.owner = owner
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    def post(self, url, *, data, headers, allow_redirects):
        self.owner.calls.append((url, json.loads(data), headers, allow_redirects))
        return Upstream()

class Factory:
    def __init__(self): self.calls = []
    def __call__(self, **kwargs): return Session(self, **kwargs)

class BrokerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = Factory()
        self.app = create_app(key_resolver=lambda role: {"cho": CHO, "coo": COO}[role],
            credential_resolver=lambda: (UPSTREAM, "upstream-secret", {"originator": "hermes-agent"}),
            http_factory=self.fake)
        self.server = TestServer(self.app)
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    def auth(self, role="cho"):
        return {"Authorization": "Bearer " + {"cho": CHO, "coo": COO}[role]}

    def payload(self, **extra):
        return {"model":"gpt-6-luna","input":"hi","store":False,"stream":True, **extra}

    async def test_missing_bearer_denied(self):
        r = await self.client.get("/p/cho/v1/models")
        self.assertEqual(r.status, 401)

    async def test_foreign_role_bearer_denied(self):
        r = await self.client.get("/p/cho/v1/models", headers=self.auth("coo"))
        self.assertEqual(r.status, 401)

    async def test_role_bearer_allowed(self):
        r = await self.client.get("/p/cho/v1/models", headers=self.auth())
        self.assertEqual(r.status, 200)

    async def test_unknown_role_denied(self):
        r = await self.client.get("/p/root/v1/models", headers=self.auth())
        self.assertEqual(r.status, 404)

    async def test_model_allowlist(self):
        r = await self.client.post("/p/cho/v1/responses", json=self.payload(model="outside"), headers=self.auth())
        self.assertEqual(r.status, 403)
        self.assertFalse(self.fake.calls)

    async def test_stream_and_store_guard(self):
        r = await self.client.post("/p/cho/v1/responses", json=self.payload(stream=False), headers=self.auth())
        self.assertEqual(r.status, 400)
        self.assertFalse(self.fake.calls)

    async def test_forward_exact_upstream_not_client_headers(self):
        r = await self.client.post("/p/cho/v1/responses", json=self.payload(),
            headers={**self.auth(), "X-Forbidden-Client": "private"})
        self.assertEqual(r.status, 200)
        self.assertIn(b"response.completed", await r.read())
        url, data, headers, redirect = self.fake.calls[0]
        self.assertEqual(url, UPSTREAM + "/responses")
        self.assertEqual(headers["Authorization"], "Bearer upstream-secret")
        self.assertNotIn("X-Forbidden-Client", headers)
        self.assertFalse(redirect)

    async def test_authenticated_same_role_concurrency_rejected(self):
        capacity = self.app["capacity"]
        ok, code = await capacity.admit("cho")
        self.assertTrue(ok, code)
        try:
            r = await self.client.post("/p/cho/v1/responses",
                json=self.payload(), headers=self.auth())
            self.assertEqual(r.status, 429)
            self.assertFalse(self.fake.calls)
        finally:
            await capacity.release("cho")

    async def test_per_role_rate_limit_preserves_other_role(self):
        capacity = self.app["capacity"]
        for _ in range(capacity.quota):
            ok, message = await capacity.admit("cho")
            self.assertTrue(ok, message)
            await capacity.release("cho")
        denied = await self.client.post("/p/cho/v1/responses",
            json=self.payload(), headers=self.auth())
        self.assertEqual(denied.status, 429)
        self.assertFalse(self.fake.calls)
        other = await self.client.post("/p/coo/v1/responses",
            json=self.payload(), headers=self.auth("coo"))
        self.assertEqual(other.status, 200)
        self.assertEqual(len(self.fake.calls), 1)

    async def test_wrong_role_does_not_consume_capacity(self):
        rejected = await self.client.post("/p/cho/v1/responses",
            json=self.payload(), headers=self.auth("coo"))
        self.assertEqual(rejected.status, 401)
        self.assertEqual(len(self.app["capacity"]._calls["cho"]), 0)
        ok = await self.client.post("/p/cho/v1/responses",
            json=self.payload(), headers=self.auth())
        self.assertEqual(ok.status, 200)

    async def test_invalid_payload_does_not_exhaust_role_quota(self):
        # Regression: eight authenticated HTTP 415s must not starve
        # the next legitimate request with 429.
        for _ in range(self.app["capacity"].quota):
            rejected = await self.client.post("/p/cho/v1/responses",
                data="not-json", headers={**self.auth(), "Content-Type": "text/plain"})
            self.assertEqual(rejected.status, 415)
            await rejected.read()
        self.assertEqual(len(self.app["capacity"]._calls["cho"]), 0)
        accepted = await self.client.post("/p/cho/v1/responses",
            json=self.payload(), headers=self.auth())
        self.assertEqual(accepted.status, 200)
        self.assertEqual(len(self.fake.calls), 1)

    async def test_disallowed_model_does_not_exhaust_role_quota(self):
        for _ in range(self.app["capacity"].quota):
            rejected = await self.client.post("/p/cho/v1/responses",
                json=self.payload(model="invalid"), headers=self.auth())
            self.assertEqual(rejected.status, 403)
            await rejected.read()
        self.assertEqual(len(self.app["capacity"]._calls["cho"]), 0)
        accepted = await self.client.post("/p/cho/v1/responses",
            json=self.payload(), headers=self.auth())
        self.assertEqual(accepted.status, 200)

    async def test_no_other_endpoint(self):
        r = await self.client.post("/p/cho/v1/chat/completions",json={},headers=self.auth())
        self.assertEqual(r.status, 404)

    async def test_upstream_auth_error_is_redacted(self):
        self.app["credential_resolver"] = lambda: (_ for _ in ()).throw(RuntimeError("SECRET-UPSTREAM-AUTH"))
        r = await self.client.post("/p/cho/v1/responses", json=self.payload(), headers=self.auth())
        self.assertEqual(r.status, 503)
        self.assertNotIn("SECRET-UPSTREAM-AUTH", await r.text())

    def test_private_key_and_mode(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "cho"
            directory.mkdir(mode=0o700)
            key = directory / "api-key"
            key.write_text(CHO)
            key.chmod(0o600)
            self.assertEqual(role_secret("cho", Path(root)), CHO)
            key.chmod(0o644)
            with self.assertRaises(ValueError):
                role_secret("cho", Path(root))

    def test_private_directory_required(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "cho"
            directory.mkdir(mode=0o700)
            key = directory / "api-key"
            key.write_text(CHO)
            key.chmod(0o600)
            directory.chmod(0o755)
            with self.assertRaises(ValueError):
                role_secret("cho", Path(root))

    def test_path_replacement_after_open_reads_pinned_inode(self):
        """Replace visible path with symlink after open: must read original FD."""
        from unittest.mock import patch
        import os
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "cho"
            directory.mkdir(mode=0o700)
            key = directory / "api-key"
            key.write_text(CHO)
            key.chmod(0o600)
            other = Path(root) / "alternate"
            other.write_text("ATTACKER-CONTROLLED-BYTES" * 4)
            other.chmod(0o600)
            original_open = os.open
            swapped = [False]
            def interpose(path, flags, *args, **kwargs):
                fd = original_open(path, flags, *args, **kwargs)
                if path == "api-key" and not swapped[0]:
                    swapped[0] = True
                    key.rename(directory / "previous")
                    key.symlink_to(other)
                return fd
            with patch("codex_role_broker.os.open", side_effect=interpose):
                result = role_secret("cho", Path(root))
            self.assertTrue(swapped[0])
            self.assertEqual(result, CHO)

    def test_broker_refuses_root_without_accessing_oauth(self):
        """Privileged launch must stop before opening service or credentials."""
        from unittest.mock import patch
        import codex_role_broker as broker
        with patch.object(broker.os, "geteuid", return_value=0), \
             patch.object(broker.web, "run_app", side_effect=AssertionError("unexpected listener")), \
             patch.object(broker, "create_app", side_effect=AssertionError("unexpected OAuth setup")):
            with self.assertRaisesRegex(RuntimeError, "broker_must_be_unprivileged"):
                broker.main()

    def test_symlink_denied(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "cho"
            directory.mkdir(mode=0o700)
            actual = Path(root) / "a"
            actual.write_text(CHO)
            actual.chmod(0o600)
            (directory / "api-key").symlink_to(actual)
            with self.assertRaises(ValueError):
                role_secret("cho", Path(root))

if __name__ == "__main__":
    unittest.main()
