#!/usr/bin/env python3
"""Regression tests for RepoWise deployment evidence MCP; no production writes."""
import asyncio
import fcntl
import json
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import deployment_evidence_mcp as pub


class DeploymentPublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "product"
        self.repo.mkdir()
        (self.repo / ".repowise").mkdir()
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True, capture_output=True)
        (self.repo / "readme.txt").write_text("disposable source")
        subprocess.run(["git", "-C", str(self.repo), "add", "readme.txt"], check=True, capture_output=True)
        subprocess.run([
            "git", "-C", str(self.repo), "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "base"
        ], check=True, capture_output=True)
        self.sha = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"],
                                  check=True, capture_output=True, text=True).stdout.strip()
        self.old_root = pub.ROOT
        pub.ROOT = self.root
        self.addCleanup(setattr, pub, "ROOT", self.old_root)
        self.lock_path = self.root / "repowise-sync.lock"
        self.lock_path.touch()
        self.scope = patch.dict("os.environ", {
            "DEPLOY_EVIDENCE_ALLOWED_REPO": "product",
            "DEPLOY_EVIDENCE_SYNC_LOCK": str(self.lock_path),
        })
        self.scope.start()
        self.addCleanup(self.scope.stop)

    def submit(self, **override):
        args = dict(repo="product", source_sha=self.sha,
                    issue="ZARI-240", deployment_id="test-observation")
        args.update(override)
        return pub.publish_deployment_observation(**args)

    def test_native_write_and_exact_readback(self):
        with patch.object(pub, "_live_product", return_value=(self.sha, 200)):
            a = self.submit()
            b = self.submit()
        self.assertTrue(a["stored"])
        self.assertTrue(a["created"])
        self.assertFalse(b["created"])
        self.assertEqual(a["episode_id"], b["episode_id"])
        got = pub.get_deployment_observation("product", a["episode_id"])
        self.assertTrue(got["found"])
        self.assertEqual(got["evidence"]["source_sha"], self.sha)
        self.assertEqual(got["evidence"]["status"], "PARTIAL_LIVE_OBSERVED")
        self.assertEqual(got["evidence"]["rollback"], "NOT_RUN")

    def test_false_production_claim_cannot_be_published(self):
        for marker, http in ((None, None), ("0" * 40, 200), (self.sha, 503)):
            with self.subTest(marker=marker, http=http):
                with patch.object(pub, "_live_product", return_value=(marker, http)):
                    self.assertEqual(self.submit()["error"], "production_readback_not_matching_source")
        self.assertFalse(pub.default_store_path(self.repo).exists())

    def test_invalid_sha_issue_deployment_and_repository(self):
        bad_cases = [
            ({"source_sha": "garbage"}, "invalid_source_sha"),
            ({"source_sha": "0" * 40}, "source_sha_not_present_in_indexed_repo"),
            ({"issue": "ZARI-0"}, "invalid_issue"),
            ({"issue": "ZARI-240;touch /tmp/pwn"}, "invalid_issue"),
            ({"deployment_id": "../../etc/passwd"}, "invalid_deployment_id"),
            ({"repo": "harness"}, "repo_out_of_scope"),
            ({"repo": "../other"}, "repo_not_allowed"),
        ]
        for changes, expected in bad_cases:
            with self.subTest(changes=changes):
                self.assertEqual(self.submit(**changes)["error"], expected)

    def test_real_http_mcp_tool_call_with_disposable_auth(self):
        import socket
        import time
        import urllib.error
        import urllib.request
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        harness = self.root / "harness"
        self.repo.rename(harness)
        token_file = self.root / "http-e2e-token"
        # Public, disposable fixture string. NEVER use a real provider key.
        throwaway = "HTTP_E2E_FAKE_TOKEN_NO_SECRET_20261118_abcdefghijklmnopqrstuvwxyz"
        token_file.write_text(throwaway)
        token_file.chmod(0o600)
        env = dict(os.environ)
        env.update({
            "DEPLOY_EVIDENCE_ROOT": str(self.root),
            "DEPLOY_EVIDENCE_ALLOWED_REPO": "harness",
            "DEPLOY_EVIDENCE_SYNC_LOCK": str(self.lock_path),
            "DEPLOY_EVIDENCE_TOKEN_FILE": str(token_file),
        })
        server = subprocess.Popen(
            [sys.executable, str(Path(pub.__file__).resolve()), "--http"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        url = "http://127.0.0.1:7339/mcp"
        try:
            started = False
            for _ in range(40):
                if server.poll() is not None:
                    self.fail("HTTP MCP exited before startup")
                with socket.socket() as sock:
                    if sock.connect_ex(("127.0.0.1", 7339)) == 0:
                        started = True
                        break
                time.sleep(0.1)
            self.assertTrue(started, "HTTP MCP did not start")
            for header in (None, "Bearer wrong-test-token"):
                req = urllib.request.Request(
                    url, headers={} if header is None else {"Authorization": header}
                )
                with self.assertRaises(urllib.error.HTTPError) as refused:
                    urllib.request.urlopen(req, timeout=3)
                self.assertEqual(refused.exception.code, 401)

            async def probe():
                async with streamablehttp_client(
                    url, headers={"Authorization": "Bearer " + throwaway}
                ) as (reader, writer, _):
                    async with ClientSession(reader, writer) as client:
                        info = await client.initialize()
                        self.assertEqual(info.serverInfo.name, "repowise-deployment-evidence")
                        catalog = await client.list_tools()
                        self.assertIn("publish_deployment_observation",
                                      [x.name for x in catalog.tools])
                        request = {
                            "repo": "harness", "source_sha": self.sha,
                            "issue": "ZARI-240", "deployment_id": "disposable-test",
                        }
                        ret = await client.call_tool("publish_deployment_observation", request)
                        value = json.loads("".join(getattr(c, "text", "") for c in ret.content))
                        self.assertTrue(value["stored"])
                        self.assertEqual(value["status"], "SOURCE_ONLY_NOT_LIVE_VERIFIED")
                        ret = await client.call_tool(
                            "get_deployment_observation",
                            {"repo": "harness", "episode_id": value["episode_id"]},
                        )
                        got = json.loads("".join(getattr(c, "text", "") for c in ret.content))
                        self.assertTrue(got["found"])
                        self.assertEqual(got["evidence"]["source_sha"], self.sha)
                        ret = await client.call_tool(
                            "publish_deployment_observation", {**request, "repo": "product"}
                        )
                        refused = json.loads("".join(getattr(c, "text", "") for c in ret.content))
                        self.assertFalse(refused["stored"])
                        self.assertEqual(refused["error"], "repo_out_of_scope")

            asyncio.run(probe())
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=3)

    def test_server_scope_is_required_and_enforced(self):
        with patch.dict("os.environ", {"DEPLOY_EVIDENCE_ALLOWED_REPO": ""}):
            self.assertEqual(self.submit()["error"], "server_repo_scope_missing")
        with patch.dict("os.environ", {"DEPLOY_EVIDENCE_ALLOWED_REPO": "harness"}):
            self.assertEqual(self.submit()["error"], "repo_out_of_scope")

    def test_read_not_found_does_not_create_database(self):
        self.assertFalse(pub.default_store_path(self.repo).exists())
        self.assertFalse(pub.get_deployment_observation("product", "0" * 16)["found"])
        self.assertFalse(pub.default_store_path(self.repo).exists())

    def test_sync_lock_refuses_race_without_touching_store(self):
        with self.lock_path.open("rb") as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(pub, "_live_product", return_value=(self.sha, 200)):
                result = self.submit()
            self.assertEqual(result["error"], "sync_in_progress")
            self.assertFalse(pub.default_store_path(self.repo).exists())
        with patch.dict("os.environ", {"DEPLOY_EVIDENCE_SYNC_LOCK": str(self.root / "nonexistent")}):
            with patch.object(pub, "_live_product", return_value=(self.sha, 200)):
                result = self.submit()
            self.assertEqual(result["error"], "sync_lock_unavailable")
            self.assertFalse(pub.default_store_path(self.repo).exists())

    def test_sync_lock_symlink_fails_closed(self):
        link = self.root / "link.lock"
        link.symlink_to(self.lock_path)
        with patch.dict("os.environ", {"DEPLOY_EVIDENCE_SYNC_LOCK": str(link)}):
            with patch.object(pub, "_live_product", return_value=(self.sha, 200)):
                result = self.s

... [4372 characters truncated]