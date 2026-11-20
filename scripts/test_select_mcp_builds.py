"""Regression tests for main-only, source-scoped automatic MCP artifact builds."""
import unittest
import select_mcp_builds as images


class McpBuildSelectionTests(unittest.TestCase):
    def test_single_mcp_path_selects_only_its_image(self):
        self.assertEqual(images.select(
            ["docs/README.md", "plasmic-mcp/src/index.ts"],
            event_name="push"),
            [{"service": "plasmic-mcp", "directory": "plasmic-mcp"}])

    def test_unrelated_or_held_external_paths_never_trigger_builds(self):
        self.assertEqual(images.select(
            ["ops/repowise/Dockerfile.publisher", "qdrant-mcp/Dockerfile",
             "paperclip-mcp/Dockerfile", "comfyui-mcp/patch-v1.mjs"],
            event_name="push"), [])

    def test_workflow_or_selection_change_builds_full_reviewed_set(self):
        selected = images.select(
            [".github/workflows/mcp-images-ghcr.yml"],
            event_name="push")
        self.assertEqual({x["service"] for x in selected},
                         set(images.MCP_BUILD_CONTEXTS))

    def test_manual_dispatch_accepts_exact_allowlist(self):
        for service in images.MCP_BUILD_CONTEXTS:
            self.assertEqual(images.select([], event_name="workflow_dispatch",
                manual_service=service),
                [{"service": service, "directory": service}])
        self.assertEqual(len(images.select([], event_name="workflow_dispatch",
                                           manual_service="all")), 6)

    def test_rejects_injected_service_and_untrusted_events(self):
        for candidate in ("../../etc", "ops", "mcp-all; touch /tmp/unsafe",
                          "qdrant-mcp", ""):
            with self.subTest(service=candidate):
                with self.assertRaisesRegex(ValueError,
                                            "invalid_manually_selected_service"):
                    images.select([], event_name="workflow_dispatch",
                                  manual_service=candidate)
        with self.assertRaisesRegex(ValueError, "untrusted_event"):
            images.select([], event_name="pull_request")

    def test_allowlist_has_real_dockerfiles(self):
        from pathlib import Path
        repo = Path(__file__).resolve().parent.parent
        for service, directory in images.MCP_BUILD_CONTEXTS.items():
            with self.subTest(service=service):
                self.assertTrue((repo / directory / "Dockerfile").is_file())


if __name__ == "__main__":
    unittest.main()
