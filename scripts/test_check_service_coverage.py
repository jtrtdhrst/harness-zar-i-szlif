import json
import tempfile
import unittest
from pathlib import Path

from check_service_coverage import check


class ServiceCoverageTests(unittest.TestCase):
    def fixture(self, entry, workflow="name: test\non:\n  pull_request:\n    paths:\n      - \"svc/**\"\n"):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "svc").mkdir()
        (root / ".github/workflows").mkdir(parents=True)
        (root / ".github/workflows/test.yml").write_text(workflow)
        (root / "scripts").mkdir()
        config = {"schema_version": 1, "entries": {"svc": entry, ".github": {"mode": "manual_only", "reason": "definitions"}, "scripts": {"mode": "manual_only", "reason": "tooling"}}}
        config_path = root / "coverage.json"
        config_path.write_text(json.dumps(config))
        return temp, root, config_path

    def test_accepts_targeted_workflow_and_explicit_manual_only(self):
        temp, root, config = self.fixture({"mode": "workflow", "workflows": [".github/workflows/test.yml"]})
        with temp:
            self.assertEqual(check(root, config), (3, 1))

    def test_accepts_unfiltered_pr_event_for_any_root(self):
        workflow = "name: test\non:\n  pull_request:\n  push:\n    branches: [main]\n"
        temp, root, config = self.fixture(
            {"mode": "workflow", "workflows": [".github/workflows/test.yml"]}, workflow
        )
        with temp:
            self.assertEqual(check(root, config), (3, 1))

    def test_push_paths_cannot_mask_a_pull_request_gap(self):
        workflow = (
            "name: test\non:\n  pull_request:\n    paths:\n"
            "      - 'other/**'\n  push:\n    branches: [main]\n"
            "    paths:\n      - 'svc/**'\n"
        )
        temp, root, config = self.fixture(
            {"mode": "workflow", "workflows": [".github/workflows/test.yml"]}, workflow
        )
        with temp:
            with self.assertRaisesRegex(ValueError, "does not path-filter"):
                check(root, config)

    def test_rejects_unclassified_new_root(self):
        temp, root, config = self.fixture({"mode": "manual_only", "reason": "manual gate"})
        with temp:
            (root / "new-service").mkdir()
            with self.assertRaisesRegex(ValueError, "root coverage mismatch"):
                check(root, config)

    def test_rejects_workflow_without_targeted_path(self):
        temp, root, config = self.fixture({"mode": "workflow", "workflows": [".github/workflows/test.yml"]}, "name: test\non:\n  pull_request:\n    paths:\n      - \"other/**\"\n")
        with temp:
            with self.assertRaisesRegex(ValueError, "does not path-filter"):
                check(root, config)

    def test_rejects_narrow_descendant_path_as_root_coverage(self):
        temp, root, config = self.fixture({"mode": "workflow", "workflows": [".github/workflows/test.yml"]}, "name: test\non:\n  pull_request:\n    paths:\n      - \"svc/only-this-file.py\"\n")
        with temp:
            with self.assertRaisesRegex(ValueError, "does not path-filter"):
                check(root, config)

    def test_rejects_manual_only_without_reason(self):
        temp, root, config = self.fixture({"mode": "manual_only", "reason": ""})
        with temp:
            with self.assertRaisesRegex(ValueError, "requires a reason"):
                check(root, config)


if __name__ == "__main__":
    unittest.main()
