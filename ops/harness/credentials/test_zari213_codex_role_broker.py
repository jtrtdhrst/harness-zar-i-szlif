"""Offline-only role broker isolation tests; zero outbound OAuth or model calls."""
import asyncio
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest

SOURCE = Path(__file__).with_name("zari213-codex-role-broker.py")
spec = importlib.util.spec_from_file_location("zari213_role_broker", SOURCE)
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)


class RoleCredentialTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / "keys"
        self.root.mkdir(mode=0o700)
        self.role_dir = self.root / "cto"
        self.role_dir.mkdir(mode=0o700)
        self.key = self.role_dir / "api-key"
        self.key.write_text("fake-role-key-for-negative-synthetic-tests-only-" + "x" * 40)
        self.key.chmod(0o600)

    def read_key(self):
        return broker.role_secret("cto", root=self.root)

    def test_own_private_role_key_is_read(self):
        self.assertTrue(self.read_key().startswith("fake-role-key-"))

    def test_unknown_role_denied(self):
        with self.assertRaisesRegex(ValueError, "role_not_allowed"):
            broker.role_secret("root", root=self.root)

    def test_missing_key_denied(self):
        self.key.unlink()
        with self.assertRaisesRegex(ValueError, "role_key_path_invalid"):
            self.read_key()

    def test_symlink_secret_denied(self):
        target = self.root / "shared"
        target.write_text("fake-shared-" + "x" * 40)
        self.key.unlink()
        self.key.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "role_key_path_invalid"):
            self.read_key()

    def test_symlink_role_dir_denied(self):
        self.role_dir.rename(self.root / "real")
        self.role_dir.symlink_to(self.root / "real", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "role_key_role_directory_invalid"):
            self.read_key()

    def test_hardlinked_role_key_denied(self):
        shared = self.root / "shared"
        os.link(self.key, shared)
        with self.assertRaisesRegex(ValueError, "role_key_permissions_invalid"):
            self.read_key()

    def test_world_readable_key_denied(self):
        self.key.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "role_key_permissions_invalid"):
            self.read_key()

    def test_world_readable_role_dir_denied(self):
        self.role_dir.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "role_key_role_directory_untrusted"):
            self.read_key()

    def test_cross_role_secret_not_interchangeable(self):
        sibling = self.root / "cho"
        sibling.mkdir(mode=0o700)
        other = sibling / "api-key"
        other.write_text("fake-cho-key-for-negative-synthetic-tests-only-" + "y" * 40)
        other.chmod(0o600)
        self.assertNotEqual(self.read_key(), broker.role_secret("cho", root=self.root))

    def test_invalid_credential_length_denied(self):
        self.key.write_text("short")
        with self.assertRaisesRegex(ValueError, "role_key_length_invalid"):
            self.read_key()


class RoleCapacityTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_one_inflight_per_role(self):
        capacity = broker.RoleCapacity()
        accepted, _ = await capacity.admit("cto")
        self.assertTrue(accepted)
        accepted_again, why = await capacity.admit("cto")
        self.assertFalse(accepted_again)
        self.assertEqual(why, "capacity_exceeded")
        await capacity.release("cto")

    async def test_cross_role_total_cap(self):
        capacity = broker.RoleCapacity(max_total=1)
        a, _ = await capacity.admit("cto")
        b, reason = await capacity.admit("cho")
        self.assertTrue(a)
        self.assertFalse(b)
        self.assertEqual(reason, "capacity_exceeded")
        await capacity.release("cto")

    async def test_rate_limit_is_role_local(self):
        capacity = broker.RoleCapacity(quota=1)
        accepted, _ = await capacity.admit("cto")
        self.assertTrue(accepted)
        await capacity.release("cto")
        denied, reason = await capacity.admit("cto")
        self.assertFalse(denied)
        self.assertEqual(reason, "rate_exceeded")
        other, _ = await capacity.admit("cho")
        self.assertTrue(other)
        await capacity.release("cho")


class RoleHTTPIsolationTests(unittest.IsolatedAsyncioTestCase):
    """Real loopback HTTP handler, synthetic role keys, zero provider calls."""
    async def asyncSetUp(self):
        from aiohttp.test_utils import TestClient, TestServer
        self.keys = {"cto": "synthetic-cto-key", "cho": "synthetic-cho-key"}
        self.provider_called = False

        def key_resolver(role):
            return self.keys.get(role, "")

        def unavailable_provider():
            self.provider_called = True
            raise AssertionError("unauthorized HTTP must never call provider")

        self.server = TestServer(broker.create_app(
            key_resolver=key_resolver, credential_resolver=unavailable_provider
        ))
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_own_role_models_allowed(self):
        r = await self.client.get("/p/cto/v1/models", headers={
            "Authorization": "Bearer " + self.keys["cto"]
        })
        self.assertEqual(r.status, 200)
        payload = await r.json()
        self.assertIn("gpt-6-luna", [x["id"] for x in payload["data"]])
        self.assertFalse(self.provider_called)

    async def test_foreign_role_key_denied(self):
        r = await self.client.get("/p/cho/v1/models", headers={
            "Authorization": "Bearer " + self.keys["cto"]
        })
        self.assertEqual(r.status, 401)
        self.assertFalse(self.provider_called)

    async def test_missing_role_key_denied(self):
        r = await self.client.get("/p/cto/v1/models")
        self.assertEqual(r.status, 401)
        self.assertFalse(self.provider_called)

    async def test_unknown_role_denied(self):
        r = await self.client.get("/p/unknown/v1/models", headers={
            "Authorization": "Bearer " + self.keys["cto"]
        })
        self.assertEqual(r.status, 404)
        self.assertFalse(self.provider_called)

    async def test_foreign_role_post_does_not_call_provider(self):
        r = await self.client.post("/p/cho/v1/responses", headers={
            "Authorization": "Bearer " + self.keys["cto"]
        }, json={"model": "gpt-6-luna", "input": "synthetic",
                 "stream": True, "store": False})
        self.assertEqual(r.status, 401)
        self.assertFalse(self.provider_called)

    async def test_invalid_model_never_calls_provider(self):
        r = await self.client.post("/p/cto/v1/responses", headers={
            "Authorization": "Bearer " + self.keys["cto"]
        }, json={"model": "unapproved-model", "input": "synthetic",
                 "stream": True, "store": False})
        self.assertEqual(r.status, 403)
        self.assertFalse(self.provider_called)


if __name__ == "__main__":
    unittest.main()
