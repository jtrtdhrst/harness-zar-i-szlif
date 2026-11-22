"""Exact source ownership and negative paths for four Harness runtime images."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "owned_selector", ROOT / "scripts/select_owned_runtime_builds.py")
selector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(selector)

class OwnedRuntimeSelectorTests(unittest.TestCase):
    def test_exact_four_manifest_routes(self):
        manifest = json.loads((ROOT / "ops/service-build-roots.json").read_text())
        rows = {r["id"]: r for r in manifest["resources"]}
        self.assertEqual(len(selector.SERVICE_ROOTS), 4)
        for name, (root, dockerfile) in selector.SERVICE_ROOTS.items():
            with self.subTest(service=name):
                self.assertTrue(rows[name]["source_build_ready"])
                self.assertEqual(rows[name]["source_root"], root)
                self.assertEqual(rows[name]["build_dockerfile"], dockerfile)
                self.assertTrue((ROOT / dockerfile).is_file())
                self.assertTrue((ROOT / dockerfile).resolve().is_relative_to(
                    (ROOT / root).resolve()))

    def test_own_path_never_builds_other_runtime(self):
        for name, (root, _) in selector.SERVICE_ROOTS.items():
            self.assertEqual(
                [x["service"] for x in selector.select(
                    [root + "/source.py"], event_name="push")], [name])
            for unrelated in ("archives/" + root + "/test.py",
                              root + "-other/test.py", "../" + root + "/test.py"):
                self.assertEqual(selector.select(
                    [unrelated], event_name="push"), [])

    def test_mcp_and_coolify_are_other_build_lanes(self):
        self.assertEqual(selector.select([
            "plasmic-mcp/src/index.ts", "mantic-mcp/src/index.ts",
            "coolify-mcp/src/index.ts", "opik-mcp/access-guard/guard.py",
            "scripts/test_service_build_roots.py"], event_name="push"), [])

    def test_control_change_rebuilds_only_exact_four(self):
        for control in selector.CONTROL_PATHS:
            self.assertEqual({x["service"] for x in selector.select(
                [control], event_name="push")}, set(selector.SERVICE_ROOTS))

    def test_dispatch_is_explicit_and_untrusted_inputs_denied(self):
        for name in selector.SERVICE_ROOTS:
            self.assertEqual(selector.select(
                [], event_name="workflow_dispatch", service=name)[0]["service"],
                name)
        self.assertEqual(len(selector.select(
            [], event_name="workflow_dispatch", service="all")), 4)
        for invalid in ("", "coolify-mcp", "../../etc", "plasmic-mcp",
                        "foo; echo unsafe"):
            with self.assertRaisesRegex(ValueError, "invalid_owned_runtime_service"):
                selector.select([], event_name="workflow_dispatch", service=invalid)
        with self.assertRaisesRegex(ValueError, "untrusted_event"):
            selector.select([], event_name="pull_request")

if __name__ == "__main__":
    unittest.main()
