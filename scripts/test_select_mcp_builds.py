"""Regression tests for main-only, source-scoped automatic MCP artifact builds."""
import unittest
import select_mcp_builds as images


class McpBuildSelectionTests(unittest.TestCase):
    def test_single_mcp_path_selects_only_its_image(self):
        self.assertEqual(images.select(
            ["docs/README.md", "mcp/plasmic-mcp/src/index.ts"],
            event_name="push"),
            [{"service": "plasmic-mcp", "directory": "mcp/plasmic-mcp", "dockerfile": "Dockerfile"}])

    def test_unrelated_or_held_external_paths_never_trigger_builds(self):
        self.assertEqual(images.select(
            ["ops/repowise/Dockerfile.publisher", "docs/old-not-source.txt",
             "paperclip-mcp/Dockerfile", "comfy/engine/Dockerfile"],
            event_name="push"), [])

    def test_comfy_mcp_canonical_source_is_independently_selected(self):
        selected = images.select(["mcp/comfy-mcp/output-image-refs.js"], event_name="push")
        self.assertEqual(selected, [{"service":"comfy-mcp","directory":"mcp/comfy-mcp","dockerfile":"Dockerfile"}])
        self.assertEqual(images.EXPECTED_REPOSITORY,"jtrtdhrst/harness-zar-i-szlif")

    def test_independent_mcp_build_paths(self):
        for name in ("hindsight-mcp", "opik-mcp"):
            with self.subTest(service=name):
                selected = images.select(["mcp/" + name + "/README.md"], event_name="push")
                self.assertEqual([item["service"] for item in selected], [name])

    def test_unregistered_mcp_cannot_rebuild(self):
        self.assertNotIn("unregistered-fixture-mcp",images.MCP_BUILD_CONTEXTS)
        self.assertEqual(images.select(["mcp/unregistered-fixture-mcp/server.py"],event_name="push"),[])
        with self.assertRaisesRegex(ValueError,"invalid_manually_selected_service"):
            images.select([],event_name="workflow_dispatch",manual_service="unregistered-fixture-mcp")

    def test_consecutive_pushes_do_not_lose_other_service_builds(self):
        # Every separate push must remain queued, even if an earlier build runs.
        # GitHub workflow-level concurrency has only one replaceable pending slot.
        from pathlib import Path
        workflow = (Path(__file__).resolve().parent.parent /
                    ".github" / "workflows" / "mcp-images-ghcr.yml"
                    ).read_text(encoding="utf8")
        self.assertNotIn("\nconcurrency:", workflow)
        first = images.select(["mcp/mantic-mcp/src/server.ts"], event_name="push")
        second = images.select(["mcp/playwright-mcp/idle-proxy.cjs"], event_name="push")
        self.assertEqual([item["service"] for item in first], ["mantic-mcp"])
        self.assertEqual([item["service"] for item in second], ["playwright-mcp"])
        self.assertNotEqual(first, second)

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
                [{"service": service, "directory": images.MCP_BUILD_CONTEXTS[service],
                  "dockerfile": ("Dockerfile.http" if service == "mantic-mcp" else
                                 "backend/Dockerfile" if service == "opik-mcp" else "Dockerfile")}])
        self.assertEqual(len(images.select([], event_name="workflow_dispatch",
                                           manual_service="all")), 9)

    def test_rejects_injected_service_and_untrusted_events(self):
        for candidate in ("../../etc", "ops", "mcp-all; touch /tmp/unsafe",
                          "not-a-service", ""):
            with self.subTest(service=candidate):
                with self.assertRaisesRegex(ValueError,
                                            "invalid_manually_selected_service"):
                    images.select([], event_name="workflow_dispatch",
                                  manual_service=candidate)
        with self.assertRaisesRegex(ValueError, "untrusted_event"):
            images.select([], event_name="pull_request")

    def test_mantic_artifact_is_production_http_bridge_not_stdio(self):
        mantic = images.select([], event_name="workflow_dispatch",
                               manual_service="mantic-mcp")[0]
        self.assertEqual(mantic["dockerfile"], "Dockerfile.http")
        from pathlib import Path
        path = Path(__file__).resolve().parent.parent / mantic["directory"] / mantic["dockerfile"]
        source = path.read_text(encoding="utf8")
        self.assertIn('EXPOSE 8090', source)
        self.assertIn('ENTRYPOINT ["node", "/app/bridge/bridge.mjs"]', source)
        workflow = (Path(__file__).resolve().parent.parent /
                    ".github" / "workflows" / "mcp-images-ghcr.yml").read_text(encoding="utf8")
        self.assertIn("matrix.dockerfile", workflow)
        self.assertIn('test -f "$BUILD_ROOT/$DOCKERFILE"', workflow)

    def test_allowlist_has_real_dockerfiles(self):
        from pathlib import Path
        repo = Path(__file__).resolve().parent.parent
        for service, directory in images.MCP_BUILD_CONTEXTS.items():
            with self.subTest(service=service):
                self.assertTrue((repo / directory /
                                 ("Dockerfile.http" if service == "mantic-mcp" else "backend/Dockerfile" if service == "opik-mcp" else "Dockerfile")).is_file())


if __name__ == "__main__":
    unittest.main()
