"""Offline regression tests for the production product image delivery readback.

No Docker access, network, provider token, live deployment or privileged file
mutation is used by these tests. Every external interaction is mocked.
"""
import argparse
import contextlib
import hashlib
import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import product_image_delivery as delivery


SHA = "4feef6903dc21be5da0433a77b10549bf0009661"
OLD_SHA = "98cd058155dbf4c268777246fc510324f98f7dc5"
DIGEST = "sha256:" + "a" * 64


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ReadbackRegressionTests(unittest.TestCase):
    def setUp(self):
        self.html = b"<html><body>approved release fixture</body></html>"
        self.public_html = self.html
        self.public_sha = SHA
        self.runtime_digest = DIGEST
        self.runtime_image = f"{delivery.REGISTRY}/{delivery.IMAGE}:{SHA}"
        self.runtime_state = "running"
        self.containers = [delivery.APP_UUID + "-fixture"]
        self.marker_data = {
            "schema_version": 1,
            "verified": True,
            "registry": delivery.REGISTRY,
            "runner": "zis-local-build",
            "coolify_image_app_uuid": delivery.APP_UUID,
            "sha": SHA,
            "image": self.runtime_image,
            "digest": DIGEST,
        }
        self.marker = mock.Mock()
        self.marker.stat.return_value = SimpleNamespace(
            st_uid=0, st_mode=stat.S_IFREG | 0o600, st_nlink=1)
        self.marker.read_text.side_effect = lambda: json.dumps(self.marker_data)
        self.subprocess_calls = []
        self.patches = [
            mock.patch.object(delivery, "MARKER", self.marker),
            mock.patch.object(delivery.subprocess, "run", side_effect=self.fake_run),
            mock.patch.object(delivery.urllib.request, "urlopen", side_effect=self.fake_urlopen),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def fake_run(self, argv, **kwargs):
        self.subprocess_calls.append(tuple(argv))
        if argv[:3] == ["docker", "ps", "--format"]:
            output = "\n".join(self.containers) + "\n"
        elif argv[:3] == ["docker", "inspect", "--format"]:
            output = f"{self.runtime_digest}|{self.runtime_image}|{self.runtime_state}\n"
        elif argv[:3] == ["docker", "exec", self.containers[0]]:
            if argv[3] == "cat":
                output = json.dumps({"commit": SHA, "source": "zar-i-szlif/main"})
            elif argv[3] == "sha256sum":
                output = hashlib.sha256(self.html).hexdigest() + "  /usr/share/nginx/html/index.html\n"
            else:
                raise AssertionError("unexpected exec subcommand")
        else:
            raise AssertionError("unexpected external process")
        return subprocess.CompletedProcess(argv, 0, output, "")

    def fake_urlopen(self, request, timeout=None):
        url = getattr(request, "full_url", request)
        if url == "https://panel.zariszlif.pl/":
            return FakeResponse(self.public_html)
        if url == delivery.PUBLIC_RELEASE:
            return FakeResponse(json.dumps({"commit": self.public_sha}).encode("utf-8"))
        if url == delivery.PUBLIC_HEALTH:
            return FakeResponse(b"ok")
        raise AssertionError("unexpected URL")

    def test_exact_image_and_public_html_allow_verified_noop(self):
        proof = delivery.target_readback(SHA)
        self.assertTrue(proof["ok"])
        self.assertEqual(proof["image_digest"], DIGEST)
        self.assertEqual(proof["sha"], SHA)

    def test_wrong_approved_sha_fails_closed(self):
        proof = delivery.target_readback(OLD_SHA)
        self.assertFalse(proof["ok"])
        self.assertEqual(proof["reason"], "build_attestation_mismatch")

    def test_invalid_sha_fails_before_external_calls(self):
        proof = delivery.target_readback("not-a-commit")
        self.assertFalse(proof["ok"])
        self.assertEqual(self.subprocess_calls, [])

    def test_modified_marker_rejected(self):
        self.marker_data["digest"] = "sha256:" + "b" * 64
        self.assertFalse(delivery.target_readback(SHA)["ok"])

    def test_untrusted_marker_permissions_rejected(self):
        self.marker.stat.return_value = SimpleNamespace(
            st_uid=1000, st_mode=stat.S_IFREG | 0o666, st_nlink=1)
        proof = delivery.target_readback(SHA)
        self.assertFalse(proof["ok"])
        self.assertEqual(proof["reason"], "untrusted_build_attestation")

    def test_wrong_container_image_ref_rejected(self):
        self.runtime_image = f"{delivery.REGISTRY}/{delivery.IMAGE}:{OLD_SHA}"
        self.assertEqual(delivery.target_readback(SHA)["reason"],
                         "target_runtime_digest_or_ref_mismatch")

    def test_wrong_runtime_digest_rejected(self):
        self.runtime_digest = "sha256:" + "b" * 64
        self.assertFalse(delivery.target_readback(SHA)["ok"])

    def test_nonrunning_runtime_rejected(self):
        self.runtime_state = "exited"
        self.assertFalse(delivery.target_readback(SHA)["ok"])

    def test_multiple_matching_containers_rejected(self):
        self.containers.append(delivery.APP_UUID + "-duplicate")
        self.assertEqual(delivery.target_readback(SHA)["reason"],
                         "target_container_not_unique")

    def test_public_html_drift_rejected_even_if_release_json_claims_sha(self):
        self.public_html = b"<html>stale data</html>"
        proof = delivery.target_readback(SHA)
        self.assertFalse(proof["ok"])
        self.assertEqual(proof["reason"], "public_html_not_target_container")

    def test_public_release_sha_mismatch_rejected(self):
        self.public_sha = OLD_SHA
        self.assertEqual(delivery.target_readback(SHA)["reason"],
                         "public_release_sha_mismatch")

    def test_noop_does_not_build_or_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (mock.patch.object(delivery, "STATE_DIR", root),
                  mock.patch.object(delivery, "LOCK", root / "delivery.lock"),
                  mock.patch.object(delivery, "ref_sha", return_value=SHA),
                  mock.patch.object(delivery, "build_and_push") as build,
                  mock.patch.object(delivery, "deploy") as deploy,
                  mock.patch.object(sys, "argv", ["delivery"])):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = delivery.main()
                self.assertEqual(code, 0)
                self.assertIn("already_live_verified", out.getvalue())
                build.assert_not_called()
                deploy.assert_not_called()

    def test_unverified_noop_never_builds_or_deploys(self):
        self.public_html = b"wrong image"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (mock.patch.object(delivery, "STATE_DIR", root),
                  mock.patch.object(delivery, "LOCK", root / "delivery.lock"),
                  mock.patch.object(delivery, "ref_sha", return_value=SHA),
                  mock.patch.object(delivery, "build_and_push") as build,
                  mock.patch.object(delivery, "deploy") as deploy,
                  mock.patch.object(sys, "argv", ["delivery"])):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    code = delivery.main()
                self.assertEqual(code, 1)
                self.assertIn("readback_unverified", err.getvalue())
                build.assert_not_called()
                deploy.assert_not_called()

    def test_manual_sha_must_be_exact_ci_approved_before_any_build(self):
        for supplied, expected in [
            ("../outside/build", "invalid_source_sha"),
            ("b" * 40, "sha_not_ci_approved"),
            ("A" * 40, "invalid_source_sha"),
            ("", "invalid_source_sha"),
        ]:
            with self.subTest(supplied=supplied), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with (mock.patch.object(delivery, "STATE_DIR", root),
                      mock.patch.object(delivery, "LOCK", root / "delivery.lock"),
                      mock.patch.object(delivery, "ref_sha", return_value=SHA),
                      mock.patch.object(delivery, "live_sha") as live,
                      mock.patch.object(delivery, "build_and_push") as build,
                      mock.patch.object(delivery, "deploy") as deploy,
                      mock.patch.object(sys, "argv",
                                        ["delivery", "--sha", supplied, "--plan"])):
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        code = delivery.main()
                    self.assertEqual(code, 1)
                    self.assertIn(expected, err.getvalue())
                    live.assert_not_called()
                    build.assert_not_called()
                    deploy.assert_not_called()

    def test_malformed_ci_approved_sha_is_denied_before_live_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (mock.patch.object(delivery, "STATE_DIR", root),
                  mock.patch.object(delivery, "LOCK", root / "delivery.lock"),
                  mock.patch.object(delivery, "ref_sha", return_value="../bad"),
                  mock.patch.object(delivery, "live_sha") as live,
                  mock.patch.object(delivery, "build_and_push") as build,
                  mock.patch.object(sys, "argv", ["delivery", "--plan"])):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    self.assertEqual(delivery.main(), 1)
                self.assertIn("invalid_ci_approved_sha", err.getvalue())
                live.assert_not_called()
                build.assert_not_called()

    def test_download_source_rejects_path_traversal_before_network_or_delete(self):
        with (mock.patch.object(delivery, "SOURCE_DIR", Path("/tmp/never-touch-this")),
              mock.patch.object(delivery.urllib.request, "urlopen") as network,
              mock.patch.object(delivery.shutil, "rmtree") as remove):
            with self.assertRaisesRegex(ValueError, "invalid_source_sha"):
                delivery.download_source("../../outside")
            network.assert_not_called()
            remove.assert_not_called()

    def test_exact_manual_approved_sha_can_be_planned_without_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (mock.patch.object(delivery, "STATE_DIR", root),
                  mock.patch.object(delivery, "LOCK", root / "delivery.lock"),
                  mock.patch.object(delivery, "ref_sha", return_value=SHA),
                  mock.patch.object(delivery, "live_sha", return_value=OLD_SHA),
                  mock.patch.object(delivery, "build_and_push") as build,
                  mock.patch.object(sys, "argv", ["delivery", "--sha", SHA, "--plan"])):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = delivery.main()
                self.assertEqual(code, 0)
                self.assertIn('"result": "would_deliver"', out.getvalue())
                build.assert_not_called()



if __name__ == "__main__":
    unittest.main()
