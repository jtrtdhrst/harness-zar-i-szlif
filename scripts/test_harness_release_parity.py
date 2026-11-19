"""Fail-closed runtime parity tests (no network, Docker or production writes)."""
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess

from harness_release_parity import ParityFailure, check

SOURCE = "a" * 40
OLD = "b" * 40
UUID = "a6ci2beifbinzckfnneiqnjd"


class FakeRunner:
    def __init__(self, upstream=SOURCE, local=SOURCE, revision=OLD,
                 diff=0, auth=True, ids="abc123abc123", config=None):
        self.upstream, self.local, self.revision = upstream, local, revision
        self.diff, self.auth, self.ids = diff, auth, ids
        self.config = config if config is not None else {
            "Image": "registry/plasmic-mcp:" + revision[:12],
            "Labels": {"coolify.serviceUuid": UUID}}
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if "ls-remote" in argv:
            return CompletedProcess(argv, 0 if self.auth else 128,
                self.upstream + "\trefs/heads/main\n" if self.auth else "", "")
        if "rev-parse" in argv:
            return CompletedProcess(argv, 0, 
                (self.local if "HEAD" in argv else self.revision) + "\n", "")
        if argv[:2] == ["docker", "ps"]:
            return CompletedProcess(argv, 0, self.ids + "\n", "")
        if argv[:2] == ["docker", "inspect"]:
            return CompletedProcess(argv, 0, json.dumps(self.config), "")
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
        return check(self.repo, sha, runner=runner)

    def denied(self, runner, code, sha=SOURCE):
        with self.assertRaises(ParityFailure) as caught:
            self.call(runner, sha)
        self.assertEqual(str(caught.exception), code)
        self.assertFalse(any(c[0] in ("curl", "docker") and
                         c[1] in ("run", "stop", "push") for c in runner.calls))

    def test_parity(self):
        self.assertEqual(self.call(FakeRunner())["result"], "parity_ok")

    def test_no_github_auth_fails_closed(self):
        self.denied(FakeRunner(auth=False), "upstream_main_unverifiable")

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
