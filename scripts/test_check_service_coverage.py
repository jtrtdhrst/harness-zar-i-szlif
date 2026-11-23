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


    def test_rejects_unclassified_nested_mcp_directory(self):
        temp, root, config = self.fixture({"mode": "manual_only", "reason": "manual gate"})
        with temp:
            (root / "mcp" / "brand-new-mcp").mkdir(parents=True)
            data = json.loads(config.read_text())
            data["entries"]["mcp"] = {"mode": "manual_only", "reason": "group"}
            config.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "root coverage mismatch"):
                check(root, config)

    def test_nested_mcp_workflow_must_keep_exact_pr_source_path_filter(self):
        workflow = (
            "name: nested service test\\non:\\n  pull_request:\\n    paths:\\n"
            "      - 'mcp/coolify-mcp/**'\\n"
            "      - '.github/workflows/test.yml'\\n"
        )
        temp, root, config = self.fixture(
            {"mode": "manual_only", "reason": "manual gate"}, workflow
        )
        with temp:
            (root / "mcp" / "coolify-mcp").mkdir(parents=True)
            data = json.loads(config.read_text())
            data["entries"]["mcp"] = {"mode": "manual_only", "reason": "group"}
            data["entries"]["mcp/coolify-mcp"] = {
                "mode": "workflow",
                "workflows": [".github/workflows/test.yml"],
            }
            config.write_text(json.dumps(data))
            self.assertEqual(check(root, config), (5, 1))
            ci = root / ".github/workflows/test.yml"
            ci.write_text(workflow.replace("      - 'mcp/coolify-mcp/**'\\n", ""))
            with self.assertRaisesRegex(ValueError, "does not path-filter"):
                check(root, config)

    def test_rejects_unclassified_nested_worker_directory(self):
        temp, root, config = self.fixture({"mode": "manual_only", "reason": "manual gate"})
        with temp:
            (root / "workers" / "new-worker").mkdir(parents=True)
            data = json.loads(config.read_text())
            data["entries"]["workers"] = {"mode": "manual_only", "reason": "group"}
            config.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "root coverage mismatch"):
                check(root, config)

    def test_required_test_step_rejects_missing_or_bypassed_tests(self):
        workflow = (
            "name: test\non:\n  pull_request:\njobs:\n  guard:\n"
            "    runs-on: ubuntu-latest\n    steps:\n"
            "      - name: MCP tests\n"
            "        working-directory: svc\n"
            "        run: npm test\n"
        )
        entry = {
            "mode": "workflow",
            "workflows": [".github/workflows/test.yml"],
            "required_test_step": {
                "job": "guard",
                "name": "MCP tests",
                "working_directory": "svc",
                "run": "npm test",
            },
        }
        temp, root, config = self.fixture(entry, workflow)
        with temp:
            self.assertEqual(check(root, config), (3, 1))
        for altered in (
            workflow.replace("run: npm test", "run: echo skipped"),
            workflow.replace("name: MCP tests", "name: renamed"),
            workflow.replace("working-directory: svc", "working-directory: other"),
            workflow.replace("run: npm test", "if: false\n        run: npm test"),
            workflow.replace("run: npm test", "continue-on-error: true\n        run: npm test"),
            workflow.replace("run: npm test", "run: npm test || true"),
            workflow.replace("  guard:\n", "  another_job:\n"),
        ):
            temp, root, config = self.fixture(entry, altered)
            with temp:
                with self.assertRaisesRegex(ValueError, "missing mandatory unconditional test step"):
                    check(root, config)


    def test_hardened_main_only_policy_is_covered_and_rejects_pr_or_weak_guards(self):
        workflow = (
            "name: Release Lanes Policy\n"
            "on:\n  push:\n    branches: [main]\n  workflow_dispatch:\n"
            "jobs:\n  validate-release-lanes:\n"
            "    if: github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')\n"
            "    runs-on: [self-hosted, linux, x64, local-build]\n"
            "    steps:\n      - name: Trusted main-only runner admission\n"
            "        shell: bash\n        run: |\n"
            "          test \"$GITHUB_REF\" = 'refs/heads/main'\n"
            "          test \"$GITHUB_REPOSITORY\" = 'jtrtdhrst/harness-zar-i-szlif'\n"
            "          test \"$(id -un)\" = actions-zis\n"
            "          ! test -w /var/run/docker.sock\n"
            "          ! test -r /opt/zis-actions-runner/.credentials\n"
            "      - uses: actions/checkout@v4\n        with:\n          persist-credentials: false\n"
            "      - name: MCP tests\n        working-directory: svc\n        run: npm test\n"
            "      - name: Release policy\n"
            "        run: python scripts/check-release-lanes.py --self-test\n"
        )
        entry = {
            "mode": "workflow", "workflows": [".github/workflows/release-lanes-policy.yml"],
            "required_test_step": {
                "job": "validate-release-lanes", "name": "MCP tests",
                "working_directory": "svc", "run": "npm test",
            }
        }

        def verify(source, should_pass):
            temp, root, config = self.fixture(entry, source)
            with temp:
                test = root / ".github/workflows/release-lanes-policy.yml"
                (root / ".github/workflows/test.yml").rename(test)
                if should_pass:
                    self.assertEqual(check(root, config), (3, 1))
                else:
                    with self.assertRaisesRegex(ValueError, "does not path-filter|missing mandatory"):
                        check(root, config)

        verify(workflow, True)
        mutations = (
            workflow.replace("on:\n  push:", "on:\n  pull_request:\n  push:"),
            workflow.replace("  push:\n    branches: [main]", "  push:\n    branches: [develop]"),
            workflow.replace("  workflow_dispatch:\n", ""),
            workflow.replace("    branches: [main]", "    branches: [main]\n    paths:\n      - 'svc/**'"),
            workflow.replace("    if: github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')\n", ""),
            workflow.replace('test "$(id -un)" = actions-zis', 'test "$(id -un)" = root'),
            workflow.replace("! test -w /var/run/docker.sock", "test -w /var/run/docker.sock"),
            workflow.replace("jtrtdhrst/harness-zar-i-szlif", "miloszspyrka-code/harness-zar-i-szlif"),
            workflow.replace("persist-credentials: false", "persist-credentials: true"),
            workflow.replace("run: npm test", "run: echo skipped"),
            workflow.replace("  validate-release-lanes:", "  fake-validator:"),
        )
        for mutant in mutations:
            with self.subTest(mutant=mutant[:80]):
                self.assertNotEqual(mutant, workflow)
                verify(mutant, False)



if __name__ == "__main__":
    unittest.main()
