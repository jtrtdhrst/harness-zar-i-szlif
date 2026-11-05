"""Checks that the real MCP GitOps controller gates release on native review."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import paperclip_mcp_auto_release as gate

HEAD = "a" * 40
MERGE = "b" * 40


class NativeApprovalHookTests(unittest.TestCase):
    def test_missing_local_gate_blocks_release(self):
        with patch.object(gate.os.path, "isfile", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "not installed"):
                gate.require_native_paperclip_review(47, HEAD, MERGE)

    def test_exact_sha_reaches_gate_without_bearer_credentials(self):
        captured = []
        def fake_run(argv, **kwargs):
            captured.append(list(argv))
            return SimpleNamespace(returncode=0)
        with patch.object(gate.os.path, "isfile", return_value=True), patch.object(gate, "run", side_effect=fake_run):
            gate.require_native_paperclip_review(47, HEAD, MERGE)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][-8:], ["--repo", gate.REPO, "--pr", "47",
                                         "--head-sha", HEAD, "--merge-sha", MERGE])
        self.assertNotIn("Bearer", " ".join(captured[0]))

    def test_failing_native_review_blocks_image_build(self):
        with patch.object(gate.os.path, "isfile", return_value=True), \
             patch.object(gate, "run", return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(RuntimeError, "not proven"):
                gate.require_native_paperclip_review(47, HEAD, MERGE)

    def test_plan_checks_native_review_before_claiming_ready(self):
        order = []
        def record_native(*args):
            order.append(("native", args))
        with patch.object(gate, "assert_compose_armed"), \
             patch.object(gate, "read_state", return_value={"last_checked_sha": HEAD}), \
             patch.object(gate, "remote_main", return_value=MERGE), \
             patch.object(gate, "git_clone_and_changes", return_value=("/tmp/readonly", ["paperclip-mcp/src/p1-git.ts"])), \
             patch.object(gate, "verified_pr", return_value=(47, HEAD)), \
             patch.object(gate, "require_native_paperclip_review", side_effect=record_native), \
             patch.object(gate, "run", return_value=SimpleNamespace(returncode=0)), \
             patch.object(gate, "build_image", side_effect=AssertionError("unexpected build")):
            with patch("builtins.print") as printer:
                self.assertEqual(gate.process(plan=True), 0)
                self.assertEqual(json.loads(printer.call_args[0][0])["result"], "ready")
        self.assertEqual(order, [("native", (47, HEAD, MERGE))])

    def test_plan_fails_closed_when_review_not_proven(self):
        with patch.object(gate, "assert_compose_armed"), \
             patch.object(gate, "read_state", return_value={"last_checked_sha": HEAD}), \
             patch.object(gate, "remote_main", return_value=MERGE), \
             patch.object(gate, "git_clone_and_changes", return_value=("/tmp/readonly", ["paperclip-mcp/src/p1-git.ts"])), \
             patch.object(gate, "verified_pr", return_value=(47, HEAD)), \
             patch.object(gate, "require_native_paperclip_review", side_effect=RuntimeError("review missing")), \
             patch.object(gate, "run", return_value=SimpleNamespace(returncode=0)), \
             patch.object(gate, "build_image", side_effect=AssertionError("unexpected build")):
            with self.assertRaisesRegex(RuntimeError, "review missing"):
                gate.process(plan=True)


if __name__ == "__main__":
    unittest.main()
