"""Fail-closed runtime parity tests (no network, Docker or production writes)."""
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from harness_release_parity import ParityFailure, check, check_services, read_release_state

SOURCE = "a" * 40
OLD = "b" * 40
UUID = "a6ci2beifbinzckfnneiqnjd"
DIGEST = "sha256:" + "d" * 64
IMAGE_ID = "sha256:" + "e" * 64
REF = "127.0.0.1:5000/harness-plasmic-mcp@" + DIGEST


class FakeRunner:
    def __init__(self, upstream=SOURCE, local=SOURCE, revision=OLD,
                 diff=0, auth=True, ids="abc123abc123", config=None,
                 remote_url="https://github.com/miloszspyrka-code/harness-zar-i-szlif.git",
                 repo_digests=None):
        self.upstream, self.local, self.revision = upstream, local, revision
        self.diff, self.auth, self.ids = diff, auth, ids
        self.remote_url = remote_url
        self.repo_digests = repo_digests if repo_digests is not None else [REF]
        self.config = config if config is not None else {
            "Image": REF,
            "Labels": {"coolify.serviceUuid": UUID,
                       "org.opencontainers.image.revision": OLD}}
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if "remote" in argv and "get-url" in argv:
            return CompletedProcess(argv, 0, self.remote_url + "\n", "")
        if "ls-remote" in argv:
            return CompletedProcess(argv, 0 if self.auth else 128,
                self.upstream + "\trefs/heads/main\n" if self.auth else "", "")
        if "rev-parse" in argv:
            return CompletedProcess(argv, 0, 
                (self.local if "HEAD" in argv else self.revision) + "\n", "")
        if argv[:2] == ["docker", "ps"]:
            return CompletedProcess(argv, 0, self.ids + "\n", "")
        if argv[:3] == ["docker", "image", "inspect"]:
            return CompletedProcess(argv, 0, json.dumps(self.repo_digests), "")
        if argv[:2] == ["docker", "inspect"]:
            # The adapter must never ask Docker for .Config or its Env secrets.
            projection = (json.dumps(self.config.get("Labels")) + "\n"
                          + json.dumps(self.config.get("Image")) + "\n"
                          + json.dumps(IMAGE_ID) + "\n")
            return CompletedProcess(argv, 0, projection, "")
        if "diff" in argv:
            return CompletedProcess(argv, self.diff, "", "")
        raise AssertionError(argv)


class ParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / "ops").mkdir()
        (self.repo / "plasmic-mcp").mkdir()
        (self.repo / "ops/release-lanes.json").write_text(json.dumps({
            "lanes": [], "other_resources": [
                {"id": "plasmic-mcp", "platform": "coolify",
                 "coolify_uuid": UUID}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, runner, sha=SOURCE):
        trusted = {"source_sha": OLD, "image_digest": DIGEST,
                   "coolify_uuid": UUID}
        with patch("harness_release_parity.read_release_state", return_value=trusted):
            return check(self.repo, sha, runner=runner)

    def denied(self, runner, code, sha=SOURCE):
        with self.assertRaises(ParityFailure) as caught:
            self.call(runner, sha)
        self.assertEqual(str(caught.exception), code)
        self.assertFalse(any(c[0] in ("curl", "docker") and
                         c[1] in ("run", "stop", "push") for c in runner.calls))

    def test_secondary_service_drift_blocks_global_no_change(self):
        runner = FakeRunner()
        with patch("harness_release_parity._check_runtime",
                   side_effect=[{"result": "parity_ok", "service": "plasmic-mcp"},
                                ParityFailure("service_changes_not_deployed")]) as runtime:
            with self.assertRaisesRegex(
                    ParityFailure, "emailens-mcp:service_changes_not_deployed"):
                check_services(self.repo, SOURCE,
                               ["plasmic-mcp", "emailens-mcp"], runner=runner)
        self.assertEqual(runtime.call_count, 2)
        self.assertEqual(sum("ls-remote" in args for args in runner.calls), 1)

    def test_no_managed_services_fails_closed(self):
        with self.assertRaisesRegex(
                ParityFailure, "managed_service_scope_missing_or_ambiguous"):
            check_services(self.repo, SOURCE, [], runner=FakeRunner())

    def test_parity(self):
        self.assertEqual(self.call(FakeRunner())["result"], "parity_ok")

    def test_no_github_auth_fails_closed(self):
        self.denied(FakeRunner(auth=False), "upstream_main_unverifiable")

    def test_wrong_origin_denied_before_contacting_remote(self):
        for url in (
            "https://github.com/other-org/harness-zar-i-szlif.git",
            "https://github.com/miloszspyrka-code/harness-zar-i-szlif.git.evil",
            "https://github.com.evil/miloszspyrka-code/harness-zar-i-szlif.git",
            "https://secret@github.com/miloszspyrka-code/harness-zar-i-szlif.git",
            "file:///tmp/masquerading-origin",
        ):
            with self.subTest(url=url):
                runner = FakeRunner(remote_url=url)
                self.denied(runner, "source_remote_untrusted")
                self.assertFalse(any("ls-remote" in call for call in runner.calls))

    def test_runtime_inspect_never_requests_container_environment(self):
        runner = FakeRunner(config={
            "Labels": {"coolify.serviceUuid": UUID,
                       "org.opencontainers.image.revision": OLD},
            "Image": REF,
            "Env": ["SECRET_VALUE_SHOULD_NOT_BE_REQUESTED=123"],
        })
        self.assertEqual(self.call(runner)["result"], "parity_ok")
        inspect = next(call for call in runner.calls if call[:2] == ["docker", "inspect"])
        self.assertIn(".Config.Labels", inspect[-1])
        self.assertIn(".Config.Image", inspect[-1])
        self.assertNotIn("json .Config}}", inspect[-1])
        self.assertNotIn(".Config.Env", inspect[-1])


    def test_mutable_tag_with_forged_current_label_is_not_parity(self):
        self.denied(FakeRunner(config={
            "Image": "registry/plasmic-mcp:latest",
            "Labels": {"coolify.serviceUuid": UUID,
                       "org.opencontainers.image.revision": SOURCE}}),
            "runtime_image_reference_mutable_or_mismatched")

    def test_wrong_running_digest_denied_even_with_valid_revision(self):
        self.denied(FakeRunner(repo_digests=["registry/plasmic-mcp@" + "sha256:" + "c" * 64]),
                    "runtime_digest_mismatch")

    def test_root_release_state_required(self):
        with patch("harness_release_parity.read_release_state",
                   side_effect=ParityFailure("release_state_unverifiable")):
            with self.assertRaisesRegex(ParityFailure, "release_state_unverifiable"):
                check(self.repo, SOURCE, runner=FakeRunner())

    def test_forged_image_revision_denied_against_trusted_state(self):
        self.denied(FakeRunner(config={
            "Image": REF,
            "Labels": {"coolify.serviceUuid": UUID,
                       "org.opencontainers.image.revision": SOURCE}}),
            "release_provenance_revision_mismatch")

    def test_missing_service_in_release_state_fails_closed(self):
        with patch("harness_release_parity.read_trusted_bytes",
                   return_value=json.dumps({}).encode()):
            with self.assertRaisesRegex(ParityFailure, "release_state_service_missing"):
                read_release_state("plasmic-mcp")

    def test_stale_source_range(self):
        self.denied(FakeRunner(upstream=OLD), "source_range_stale")

    def test_stale_checkout(self):
        self.denied(FakeRunner(local=OLD), "checkout_stale")

    def test_old_running_image_with_service_delta(self):
        self.denied(FakeRunner(diff=1), "service_changes_not_deployed")

    def test_no_runtime_revision_label_or_sha_tag(self):
        self.denied(FakeRunner(config={"Image": "plasmic:latest",
                                     "Labels": {"coolify.serviceUuid": UUID}}),
                    "runtime_revision_missing")

    def test_wrong_coolify_uuid(self):
        self.denied(FakeRunner(config={"Image": "plasmic:" + OLD[:12],
                                     "Labels": {"coolify.serviceUuid": "wrong"}}),
                    "runtime_uuid_mismatch")

    def test_two_containers(self):
        self.denied(FakeRunner(ids="abc123abc123\ndef456def456"),
                    "runtime_missing_or_ambiguous")

    def test_unknown_diff_error(self):
        self.denied(FakeRunner(diff=128), "service_diff_unverifiable")

    def test_invalid_sha(self):
        self.denied(FakeRunner(), "expected_sha_invalid", "not-a-sha")


if __name__ == "__main__":
    unittest.main()
