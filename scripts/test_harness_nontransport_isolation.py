#!/usr/bin/env python3
"""Regression: separate Coolify resources and deleted folders never bypass admission."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import harness_native_delivery as delivery

OLD = "0" * 40
NEW = "f" * 40


def manifest(*, auto=False):
    return {
        "lanes": [],
        "other_resources": [
            {"id": "plasmic", "platform": "coolify", "coolify_kind": "service",
             "coolify_uuid": "p" * 24, "review_required": True,
             "auto_deploy_expected": auto},
            {"id": "qdrant", "platform": "coolify", "coolify_kind": "service",
             "coolify_uuid": "q" * 24, "review_required": True,
             "auto_deploy_expected": False},
        ],
    }


class FakeHost:
    def __init__(self):
        self.mutations = []

    def docker(self, *args, **kwargs):
        self.mutations.append(("docker", args))
        raise AssertionError("No Docker actions allowed")

    def coolify(self, *args, **kwargs):
        self.mutations.append(("coolify", args))
        raise AssertionError("No Coolify actions allowed")


class NontransportIsolationTests(unittest.TestCase):
    def run_plan(self, changed, manifest_data, directory):
        fake = FakeHost()
        with patch.object(delivery, "Host", return_value=fake), \
             patch.object(delivery, "load_gate_file", return_value=manifest_data), \
             patch.object(delivery, "git_changed_paths", return_value=changed), \
             patch("sys.stdout", new_callable=io.StringIO) as output, \
             patch("sys.stderr", new_callable=io.StringIO) as error:
            rc = delivery.main([
                "--mode", "plan", "--repo", str(directory),
                "--base-sha", OLD, "--source-sha", NEW,
            ])
            return rc, output.getvalue(), error.getvalue(), fake.mutations

    def test_explicitly_manual_external_lanes_are_pending_not_deployed(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = ["plasmic/studio/nginx.conf", "qdrant/README.md"]
            rc, out, err, mutations = self.run_plan(paths, manifest(), temp)
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        self.assertEqual(data["result"], "pending_nontransport_changes")
        self.assertEqual(data["pending_external_resources"], ["plasmic", "qdrant"])
        self.assertEqual(data["pending_paths"], paths)
        self.assertEqual(data["admitted"], [])
        self.assertEqual(data["services"], {})
        self.assertEqual(mutations, [])

    def test_missing_native_source_is_pending_retirement_not_build(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = ["paperclip-mcp/deploy/entrypoint.sh"]
            rc, out, err, mutations = self.run_plan(paths, manifest(), temp)
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        self.assertEqual(data["result"], "pending_nontransport_changes")
        self.assertEqual(data["pending_retired_resources"], ["paperclip-mcp"])
        self.assertEqual(data["pending_paths"], paths)
        self.assertEqual(mutations, [])

    def test_external_with_auto_deploy_expectation_still_denies(self):
        with tempfile.TemporaryDirectory() as temp:
            rc, out, err, mutations = self.run_plan(
                ["plasmic/src/index.ts"], manifest(auto=True), temp)
        self.assertEqual(rc, 1)
        self.assertIn("service_not_in_transport:plasmic", err)
        self.assertEqual(out, "")
        self.assertEqual(mutations, [])

    def test_nontransport_changes_must_not_erase_native_hold(self):
        # Even a separately deferred resource must not turn a held native
        # service into an implicitly admitted release.
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "plasmic-mcp").mkdir()
            man = manifest()
            man["other_resources"].append({
                "id": "plasmic-mcp", "platform": "coolify",
                "coolify_uuid": "s" * 24, "review_required": True,
                "auto_deploy_expected": False})
            rc, out, err, mutations = self.run_plan(
                ["plasmic-mcp/src/index.js", "qdrant/README.md"], man, temp)
        self.assertEqual(rc, 1)
        data = json.loads(out)
        self.assertEqual(data["pending_external_resources"], ["qdrant"])
        self.assertEqual(data["pending_paths"], ["qdrant/README.md"])
        self.assertIn("plasmic-mcp", data["denied"])
        self.assertEqual(data["result"], "denied")
        self.assertEqual(mutations, [])


if __name__ == "__main__":
    unittest.main()
