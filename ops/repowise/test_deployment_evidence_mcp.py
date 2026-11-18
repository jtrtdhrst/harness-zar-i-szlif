#!/usr/bin/env python3
"""Regression tests for RepoWise deployment evidence MCP; no production writes."""
import json
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
        self.scope = patch.dict("os.environ", {"DEPLOY_EVIDENCE_ALLOWED_REPO": "product"})
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

    def test_server_scope_is_required_and_enforced(self):
        with patch.dict("os.environ", {"DEPLOY_EVIDENCE_ALLOWED_REPO": ""}):
            self.assertEqual(self.submit()["error"], "server_repo_scope_missing")
        with patch.dict("os.environ", {"DEPLOY_EVIDENCE_ALLOWED_REPO": "harness"}):
            self.assertEqual(self.submit()["error"], "repo_out_of_scope")

    def test_read_not_found_does_not_create_database(self):
        self.assertFalse(pub.default_store_path(self.repo).exists())
        self.assertFalse(pub.get_deployment_observation("product", "0" * 16)["found"])
        self.assertFalse(pub.default_store_path(self.repo).exists())

    def test_deny_symlink_escape(self):
        (self.root / "harness").symlink_to(self.root.parent, target_is_directory=True)
        with patch.dict("os.environ", {"DEPLOY_EVIDENCE_ALLOWED_REPO": "harness"}):
            self.assertEqual(pub.get_deployment_observation("harness", "0" * 16)["error"],
                             "indexed_repo_unavailable")

    def test_harness_source_only_not_marked_as_live(self):
        harness = self.root / "harness"
        self.repo.rename(harness)
        with patch.dict("os.environ", {"DEPLOY_EVIDENCE_ALLOWED_REPO": "harness"}):
            with patch.object(pub, "_git_contains", return_value=True):
                data = pub.publish_deployment_observation(
                    "harness", self.sha, "ZARI-240", "test-harness")
        self.assertTrue(data["stored"])
        self.assertEqual(data["status"], "SOURCE_ONLY_NOT_LIVE_VERIFIED")
        self.assertEqual(data["independent_authenticated_positive_qa"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
