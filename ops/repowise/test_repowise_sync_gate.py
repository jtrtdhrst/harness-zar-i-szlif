#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from repowise_sync_gate import failure_reason


class RepowiseSyncGateTests(unittest.TestCase):
    def state(self, payload):
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "state.json"
        path.write_text(json.dumps(payload))
        self.addCleanup(temp.cleanup)
        return path

    def test_accepts_full_complete(self):
        path = self.state({"git_tier": "full", "index_scope": {"upgrade": {"status": "complete"}}})
        self.assertIsNone(failure_reason(path))

    def test_accepts_full_not_applicable(self):
        path = self.state({"git_tier": "full", "index_scope": {"upgrade": {"status": "not_applicable"}}})
        self.assertIsNone(failure_reason(path))

    def test_rejects_shallow_seed(self):
        path = self.state({"git_tier": "shallow", "index_scope": {"upgrade": {"status": "complete"}}})
        self.assertIn("git_tier=", failure_reason(path))

    def test_rejects_unfinished_upgrade(self):
        path = self.state({"git_tier": "full", "index_scope": {"upgrade": {"status": "pending"}}})
        self.assertIn("upgrade.status=", failure_reason(path))

    def test_rejects_missing_upgrade(self):
        path = self.state({"git_tier": "full", "index_scope": {}})
        self.assertIn("upgrade.status=", failure_reason(path))

    def test_rejects_unreadable_state(self):
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "state.json"
        path.write_text("{not-json")
        self.addCleanup(temp.cleanup)
        self.assertIn("unreadable state.json", failure_reason(path))


if __name__ == "__main__":
    unittest.main()
