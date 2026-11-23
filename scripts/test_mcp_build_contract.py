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



def evidence_step(source, action):
    """Find exactly one mandatory action step, independent of YAML key order."""
    steps = re.split(r"""(?m)(?=^      - ['"]?[a-z][a-z-]*['"]?[ \t]*:)""", source)
    matches = [step for step in steps if "uses: " + action in step]
    if len(matches) != 1:
        raise AssertionError("missing_or_duplicated_evidence_step:" + action)
    return matches[0]


def require_mandatory_evidence_action(source, action):
    """Fail closed on step/job soft failures and conditional evidence actions."""
    block = evidence_step(source, action)
    if re.search(r"""(?m)^(?:      - |        )['"]?(?:if|continue-on-error)['"]?[ \t]*:""", block):
        raise AssertionError("conditional_or_nonblocking_evidence_step:" + action)
    if re.search(r"""(?m)^    ['"]?continue-on-error['"]?[ \t]*:""", source):
        raise AssertionError("nonblocking_publisher_job:" + action)


EXPECTED_PUBLISH_IF = {
    GENERAL_FLOW: "needs.select.outputs.matrix != '[]' && github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')",
    RUNTIME_FLOW: "github.ref == 'refs/heads/main' && needs.select.outputs.matrix != '[]' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')",
    COOLIFY_FLOW: "github.event_name == 'push' && github.ref == 'refs/heads/main'",
}


def require_exact_main_publish_gate(source, flow):
    """Only an explicitly trusted-main publishing job can carry OCI identity."""
    job_name = "build-and-push" if flow == GENERAL_FLOW else "publish"
    boundaries = list(re.finditer(r"(?m)^  ([a-z][a-z0-9-]*):[ \t]*$", source))
    matches = [i for i, m in enumerate(boundaries) if m.group(1) == job_name]
    if len(matches) != 1:
        raise AssertionError("missing_or_duplicated_publish_job:" + flow)
    i = matches[0]
    body = source[boundaries[i].start():boundaries[i + 1].start() if i + 1 < len(boundaries) else len(source)]
    conditions = re.findall(r"""(?m)^    ['"]?if['"]?[ \t]*:[ \t]*(.*)$""", body)
    if conditions != [EXPECTED_PUBLISH_IF[flow]]:
        raise AssertionError("untrusted_or_conditional_publish_job:" + flow)
    if re.search(r"""(?m)^    ['"]?continue-on-error['"]?[ \t]*:""", body):
        raise AssertionError("nonblocking_publish_job:" + flow)


class McpSourceBuildContract(unittest.TestCase):
    def test_every_owned_mcp_has_exactly_one_owned_source_and_publisher(self):
        services = owned_services()
        roots = build_roots()
        self.assertEqual(len(services), 12, "Review the fleet change and update this known baseline")
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

    def test_retired_qdrant_mcp_is_excluded_from_every_build_lane(self):
        services = owned_services()
        self.assertNotIn("qdrant-mcp", services)
        self.assertNotIn("qdrant-mcp", GENERAL)
        self.assertNotIn("qdrant-mcp", RUNTIME)
        self.assertNotIn("qdrant-mcp", build_roots())
        self.assertFalse((ROOT / "mcp/qdrant-mcp").exists())
        self.assertIn("qdrant", {r["name"] for r in json.loads(REGISTRY.read_text())["resources"]})

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
                require_exact_main_publish_gate(source, flow)
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

    def test_yaml_first_key_condition_and_job_level_soft_failure_are_denied(self):
        """The valid YAML shapes found during native CHO adversarial review."""
        for flow in (GENERAL_FLOW, RUNTIME_FLOW, COOLIFY_FLOW):
            source = (WORKFLOWS / flow).read_text()
            for action in ("actions/attest@", "actions/upload-artifact@"):
                block = evidence_step(source, action)
                head = block.splitlines()[0]
                self.assertTrue(head.startswith("      - name:"), (flow, action, head))
                first_key = "      - if: always()\n        name:" + head[len("      - name:"):]
                mutated = source.replace(head, first_key, 1)
                with self.subTest(flow=flow, action=action, shape="first-key-if"):
                    with self.assertRaises(AssertionError):
                        require_mandatory_evidence_action(mutated, action)
                self.assertIn("    permissions:", source)
                job_soft_failure = source.replace("    permissions:",
                                                  "    continue-on-error: true\n    permissions:", 1)
                with self.subTest(flow=flow, action=action, shape="job-soft-failure"):
                    with self.assertRaises(AssertionError):
                        require_mandatory_evidence_action(job_soft_failure, action)

    def test_publish_job_and_yaml_spacing_bypass_regressions(self):
        """Reject valid YAML spacing variants and a bypassing job-level if."""
        for flow in (GENERAL_FLOW, RUNTIME_FLOW, COOLIFY_FLOW):
            source = (WORKFLOWS / flow).read_text()
            require_exact_main_publish_gate(source, flow)
            for action in ("actions/attest@", "actions/upload-artifact@"):
                for injected in ("        if : always()\n",
                                 "        continue-on-error : true\n"):
                    mutated = source.replace("        uses: " + action,
                                             injected + "        uses: " + action, 1)
                    with self.subTest(flow=flow, action=action, shape="spaced-key"):
                        with self.assertRaises(AssertionError):
                            require_mandatory_evidence_action(mutated, action)
            marker = "    if: " + EXPECTED_PUBLISH_IF[flow]
            self.assertIn(marker, source)
            for alt in ("    if: false", "    if : always()", marker + "\n    if: false"):
                changed = source.replace(marker, alt, 1)
                with self.subTest(flow=flow, shape="publish-job-if", alt=alt):
                    with self.assertRaises(AssertionError):
                        require_exact_main_publish_gate(changed, flow)
            changed = source.replace("    permissions:", "    continue-on-error : true\n    permissions:", 1)
            with self.subTest(flow=flow, shape="job-spaced-soft-failure"):
                with self.assertRaises(AssertionError):
                    require_exact_main_publish_gate(changed, flow)

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
