"""Fail closed when an owned Coolify MCP loses its GitHub SHA-bound image build.

Source ownership is taken from the versioned Coolify registry and build roots.
This does NOT attest an OCI digest, authorize production promotion or prove E2E.
"""
import json
import re
import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "ops/coolify-service-registry.json"
ROOTS = ROOT / "ops/service-build-roots.json"
WORKFLOWS = ROOT / ".github/workflows"
GENERAL = runpy.run_path(str(ROOT / "scripts/select_mcp_builds.py"))["MCP_BUILD_CONTEXTS"]
RUNTIME = runpy.run_path(str(ROOT / "scripts/select_owned_runtime_builds.py"))["SERVICE_ROOTS"]
GENERAL_FLOW = "mcp-images-ghcr.yml"
RUNTIME_FLOW = "owned-runtime-images-ghcr.yml"
COOLIFY_FLOW = "coolify-mcp-ci.yml"


def owned_services():
    return {
        row["name"]: row for row in json.loads(REGISTRY.read_text())["resources"]
        if row.get("source") == "owned-code" and "mcp" in row["name"]
    }


def build_roots():
    return {
        row["id"]: row for row in json.loads(ROOTS.read_text())["resources"]
    }



def require_mandatory_evidence_action(source, action):
    """Do not silently skip attest or artifact steps after a successful image push."""
    # These workflows use precisely six-space-indented top-level step entries.
    # Verify the action's own step, not a reassuring string elsewhere in YAML.
    steps = re.split(r"(?m)(?=^      - (?:name|uses):)", source)
    matches = [step for step in steps if "uses: " + action in step]
    if len(matches) != 1:
        raise AssertionError("missing_or_duplicated_evidence_step:" + action)
    block = matches[0]
    if re.search(r"(?m)^        (?:if|continue-on-error):\s*", block):
        raise AssertionError("conditional_or_nonblocking_evidence_step:" + action)


class McpSourceBuildContract(unittest.TestCase):
    def test_every_owned_mcp_has_exactly_one_owned_source_and_publisher(self):
        services = owned_services()
        roots = build_roots()
        self.assertEqual(len(services), 13, "Review the fleet change and update this known baseline")
        self.assertEqual(set(services), set(GENERAL) |
                         (set(RUNTIME) & set(services)) | {"coolify-mcp"})
        for name, row in services.items():
            with self.subTest(name=name):
                self.assertIn(name, roots)
                manifest = roots[name]
                self.assertEqual(row["uuid"], manifest["uuid"])
                self.assertTrue(manifest["source_build_ready"])
                context = row["root"]
                dockerfile = row["dockerfile"]
                self.assertEqual(manifest["source_root"], context)
                self.assertEqual(manifest["build_dockerfile"], dockerfile)
                self.assertTrue(context.startswith("mcp/"))
                self.assertTrue((ROOT / context).is_dir())
                self.assertTrue((ROOT / dockerfile).is_file())
                self.assertTrue((ROOT / dockerfile).resolve().is_relative_to(
                    (ROOT / context).resolve()))
                if name == "coolify-mcp":
                    flow = COOLIFY_FLOW
                elif name in GENERAL:
                    self.assertEqual(GENERAL[name], context)
                    flow = GENERAL_FLOW
                else:
                    self.assertEqual(RUNTIME[name], (context, dockerfile))
                    flow = RUNTIME_FLOW
                yaml = (WORKFLOWS / flow).read_text()
                self.assertIn(f"'{context}/**'", yaml,
                              f"{name}: main push path must trigger owned build")
                self.assertIn("branches: [main]", yaml)
                self.assertIn("push:", yaml)
                self.assertIn("ghcr.io/", yaml)
                self.assertIn("org.opencontainers.image.revision", yaml)

    def test_publishers_gate_exact_source_sha_and_output_digest(self):
        for flow in (GENERAL_FLOW, RUNTIME_FLOW, COOLIFY_FLOW):
            with self.subTest(workflow=flow):
                source = (WORKFLOWS / flow).read_text()
                self.assertIn("refs/heads/main", source)
                self.assertIn("git rev-parse HEAD", source)
                self.assertIn("sha-", source)
                self.assertIn("digest", source.lower())
                self.assertIn("push", source)
                self.assertIn("org.opencontainers.image.source", source)
                self.assertIn("id-token: write", source)
                self.assertIn("attestations: write", source)
                self.assertIn("actions/attest@", source)
                self.assertIn("actions/upload-artifact@", source)
                require_mandatory_evidence_action(source, "actions/attest@")
                require_mandatory_evidence_action(source, "actions/upload-artifact@")
                self.assertIn("release_authorized", source)
                self.assertIn("production_verified", source)
                self.assertNotIn("git reset --hard origin/main", source)

    def test_nonblocking_or_conditional_attestation_is_rejected(self):
        """Regress the exact soft-failure configuration identified in CTO review."""
        for flow in (GENERAL_FLOW, RUNTIME_FLOW, COOLIFY_FLOW):
            source = (WORKFLOWS / flow).read_text()
            for action in ("actions/attest@", "actions/upload-artifact@"):
                original = "        uses: " + action
                self.assertIn(original, source, (flow, action))
                for injected in ("        continue-on-error: true\n",
                                 "        if: always()\n"):
                    mutated = source.replace(original, injected + original, 1)
                    with self.subTest(workflow=flow, action=action, injected=injected):
                        with self.assertRaises(AssertionError):
                            require_mandatory_evidence_action(mutated, action)

    def test_no_unknown_vendor_image_is_falsely_marked_source_owned(self):
        rows = {
            row["name"]: row
            for row in json.loads(REGISTRY.read_text())["resources"]
        }
        expected = {
            "cloudflared-mcp": "vendor-image",
            "mcp-activation": "vendor-image",
            "repowise-mcp-runtime": "local-image-unknown-source",
            "zar-i-szlif-mcp-host": "other-repository",
            "zar-i-szlif-mcp-host-image": "other-repository",
        }
        for name, kind in expected.items():
            with self.subTest(name=name):
                self.assertEqual(rows[name]["source"], kind)
                self.assertNotIn("root", rows[name])

    def test_reviewed_pr_validates_the_contract_and_documentation(self):
        flow = (WORKFLOWS / "source-build-roots-pr.yml").read_text()
        self.assertIn("scripts/test_mcp_build_contract.py", flow)
        self.assertIn("ops/repowise/MCP_SOURCE_BUILDS.md", flow)
        self.assertIn("test_mcp_build_contract.py' -v", flow)
        self.assertTrue((ROOT / "ops/repowise/MCP_SOURCE_BUILDS.md").is_file())


if __name__ == "__main__":
    unittest.main()
