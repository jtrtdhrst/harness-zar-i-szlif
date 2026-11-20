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
REAL_READ_MARKER = delivery.read_build_attestation


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
        self.runtime_digest = "sha256:" + "b" * 64
        self.registry_digests = [f"{delivery.REGISTRY}/{delivery.IMAGE}@{DIGEST}"]
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
        self.marker_untrusted = False
        self.subprocess_calls = []
        self.patches = [
            mock.patch.object(delivery, "read_build_attestation", side_effect=self.fake_marker),
            mock.patch.object(delivery.subprocess, "run", side_effect=self.fake_run),
            mock.patch.object(delivery.urllib.request, "urlopen", side_effect=self.fake_urlopen),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def fake_marker(self, **kwargs):
        if self.marker_untrusted:
            raise PermissionError("untrusted_build_attestation")
        return self.marker_data

    def fake_run(self, argv, **kwargs):
        self.subprocess_calls.append(tuple(argv))
        if argv[:3] == ["docker", "ps", "--format"]:
            output = "\n".join(self.containers) + "\n"
        elif argv[:3] == ["docker", "inspect", "--format"]:
            output = f"{self.runtime_digest}|{self.runtime_image}|{self.runtime_state}\n"
        elif argv[:3] == ["docker", "image", "inspect"]:
            output = f"{'sha256:'+'b'*64}|{json.dumps(self.registry_digests)}\n"
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
        self.marker_untrusted = True
        proof = delivery.target_readback(SHA)
        self.assertFalse(proof["ok"])
        self.assertEqual(proof["reason"], "untrusted_build_attestation")

    def test_wrong_container_image_ref_rejected(self):
        self.runtime_image = f"{delivery.REGISTRY}/{delivery.IMAGE}:{OLD_SHA}"
        self.assertEqual(delivery.target_readback(SHA)["reason"],
                         "target_runtime_digest_or_ref_mismatch")

    def test_wrong_runtime_digest_rejected(self):
        self.runtime_digest = "sha256:" + "c" * 64
        self.assertFalse(delivery.target_readback(SHA)["ok"])

    def test_nonrunning_runtime_rejected(self):
        self.runtime_state = "exited"
        self.assertFalse(delivery.target_readback(SHA)["ok"])

    def test_multiple_matching_containers_rejected(self):
        self.containers.append(delivery.APP_UUID + "-duplicate")
        self.assertEqual(delivery.target_readback(SHA)["reason"],
                         "target_container_not_unique")

    def test_distinct_image_id_and_manifest_digest_is_accepted(self):
        self.assertNotEqual(self.runtime_digest, DIGEST)
        self.assertTrue(delivery.target_readback(SHA)["ok"])

    def test_valid_container_id_with_wrong_registry_digest_denied(self):
        self.registry_digests = [f"{delivery.REGISTRY}/{delivery.IMAGE}@sha256:{'c'*64}"]
        self.assertEqual(delivery.target_readback(SHA)["reason"],
                         "target_runtime_digest_or_ref_mismatch")

    def test_real_marker_inode_symlink_and_parent_permissions_are_denied(self):
        import os
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp) / "marker"
            parent.mkdir(mode=0o700)
            file = parent / "proof.json"
            file.write_text(json.dumps(self.marker_data))
            file.chmod(0o600)
            with mock.patch.object(delivery, "MARKER", file):
                self.assertEqual(REAL_READ_MARKER(
                    expected_uid=os.geteuid(),expected_gid=os.getegid()), self.marker_data)
                parent.chmod(0o777)
                with self.assertRaises(PermissionError):
                    REAL_READ_MARKER(
                        expected_uid=os.geteuid(),expected_gid=os.getegid())
                parent.chmod(0o700)
                link = parent / "link.json"
                link.symlink_to(file)
            with mock.patch.object(delivery, "MARKER", link):
                with self.assertRaises(OSError):
                    REAL_READ_MARKER(
                        expected_uid=os.geteuid(),expected_gid=os.getegid())

    def test_real_marker_opened_inode_not_swapped_by_replaced_path(self):
        import os
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp) / "marker"
            parent.mkdir(mode=0o700)
            file = parent / "proof.json"
            file.write_text(json.dumps(self.marker_data))
            file.chmod(0o600)
            with mock.patch.object(delivery, "MARKER", file):
                result = REAL_READ_MARKER(
                    expected_uid=os.geteuid(),expected_gid=os.getegid())
                self.assertEqual(result["sha"], SHA)

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

    def test_symlink_lock_does_not_get_followed_or_change_victim(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            victim=root/"victim"
            victim.write_text("UNCHANGED")
            link=root/"delivery.lock"
            link.symlink_to(victim)
            with (mock.patch.object(delivery,"STATE_DIR",root),
                  mock.patch.object(delivery,"LOCK",link),
                  mock.patch.object(delivery,"ref_sha") as ref,
                  mock.patch.object(sys,"argv",["delivery","--plan"])):
                err=io.StringIO()
                with contextlib.redirect_stderr(err):
                    self.assertEqual(delivery.main(),1)
                self.assertIn("untrusted_state_file",err.getvalue())
                ref.assert_not_called()
                self.assertEqual(victim.read_text(),"UNCHANGED")

    def test_symlink_build_log_is_denied_without_touching_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            victim=root/"victim"
            victim.write_text("UNCHANGED")
            link=root/"build-SHA.log"
            link.symlink_to(victim)
            with self.assertRaises(OSError):
                delivery.open_owned_state_file(link,append=True)
            self.assertEqual(victim.read_text(),"UNCHANGED")

    def test_partial_download_does_not_leave_root_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (mock.patch.object(delivery, "STATE_DIR", root),
                  mock.patch.object(delivery, "SOURCE_DIR", root / "src"),
                  mock.patch.object(delivery, "github_token", return_value="synthetic"),
                  mock.patch.object(delivery.urllib.request, "urlopen",
                                    side_effect=OSError("test network interrupted"))):
                with self.assertRaisesRegex(OSError, "network interrupted"):
                    delivery.download_source(SHA)
                self.assertEqual(list((root / "src").glob("*.tar.gz")), [])

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


    def test_insecure_existing_state_directory_denies_before_git_or_docker(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state"
            state.mkdir()
            state.chmod(0o777)
            with (mock.patch.object(delivery, "STATE_DIR", state),
                  mock.patch.object(delivery, "LOCK", state / "delivery.lock"),
                  mock.patch.object(delivery, "ref_sha") as ref,
                  mock.patch.object(delivery, "live_sha") as live,
                  mock.patch.object(sys, "argv", ["delivery", "--plan"])):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    self.assertEqual(delivery.main(), 1)
                self.assertIn("untrusted_state_directory", err.getvalue())
                ref.assert_not_called()
                live.assert_not_called()

    def test_symlink_state_directory_denies_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            real = parent / "real"
            real.mkdir(mode=0o700)
            link = parent / "link"
            link.symlink_to(real, target_is_directory=True)
            with (mock.patch.object(delivery, "STATE_DIR", link),
                  mock.patch.object(delivery, "LOCK", link / "delivery.lock"),
                  mock.patch.object(delivery, "ref_sha") as ref,
                  mock.patch.object(sys, "argv", ["delivery", "--plan"])):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    self.assertEqual(delivery.main(), 1)
                self.assertIn("untrusted_state_directory", err.getvalue())
                ref.assert_not_called()

    def test_atomic_state_save_ignores_preexisting_symlink_tmp(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            victim = parent / "victim.txt"
            victim.write_text("DO NOT MODIFY")
            dest = parent / "state.json"
            legacy_tmp = dest.with_suffix(".tmp")
            legacy_tmp.symlink_to(victim)
            with mock.patch.object(delivery, "STATE", dest):
                delivery.save({"sha": SHA})
            self.assertEqual(victim.read_text(), "DO NOT MODIFY")
            self.assertTrue(legacy_tmp.is_symlink())
            self.assertEqual(json.loads(dest.read_text()), {"sha": SHA})
            self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o600)

    def test_atomic_marker_update_ignores_preexisting_symlink_tmp(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            victim = parent / "victim.txt"
            victim.write_text("DO NOT MODIFY")
            marker = parent / "zis-image-promotion-ready.json"
            legacy_tmp = marker.with_suffix(".tmp")
            legacy_tmp.symlink_to(victim)
            with mock.patch.object(delivery, "MARKER", marker):
                delivery.update_marker(SHA, f"{delivery.REGISTRY}/{delivery.IMAGE}:{SHA}", DIGEST)
            self.assertEqual(victim.read_text(), "DO NOT MODIFY")
            self.assertTrue(legacy_tmp.is_symlink())
            data = json.loads(marker.read_text())
            self.assertEqual(data["sha"], SHA)
            self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)



if __name__ == "__main__":
    unittest.main()
