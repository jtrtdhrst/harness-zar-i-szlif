"""Fail-closed structural inventory of all Harness Coolify build roots.

This is only a source-layout assertion, not image build / release proof.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "ops" / "service-build-roots.json"
# Fail closed on local Docker COPY/ADD instructions escaping the build context.
# A literal "\\s" in this pattern would silently disable the guard.
PARENT_CONTEXT_COPY_RE = re.compile(r"(?im)^\s*(?:ADD|COPY)\s+[^\n]*\.\./")

class HarnessBuildRootsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.rows = cls.data["resources"]

    def test_exactly_16_in_repo_build_root_resources(self):
        self.assertEqual(self.data["schema_version"], 1)
        self.assertEqual(self.data["repo"], "jtrtdhrst/harness-zar-i-szlif")
        self.assertEqual(len(self.rows), 16)
        self.assertEqual(len({r["id"] for r in self.rows}), 16)
        self.assertEqual(len({r["uuid"] for r in self.rows}), 16)

    def test_every_source_root_is_non_root_and_explicit(self):
        for r in self.rows:
            with self.subTest(service=r["id"]):
                self.assertRegex(r["uuid"], r"^[a-z0-9]{24}$")
                path = r["source_root"]
                self.assertNotIn(path, ("", ".", "/"))
                self.assertNotIn("..", Path(path).parts)
                self.assertFalse(Path(path).is_absolute())
                self.assertTrue(path.strip())
                self.assertTrue(r.get("source_build_ready") is True or r.get("source_build_ready") is False)
                if not r["source_build_ready"]:
                    self.assertGreater(len(r.get("reason", "")), 30)

    def test_ready_dockerfiles_exist_inside_owned_context(self):
        ready = [r for r in self.rows if r["source_build_ready"]]
        self.assertGreaterEqual(len(ready), 10)
        for r in ready:
            with self.subTest(service=r["id"]):
                folder = (ROOT / r["source_root"]).resolve()
                dockerfile = (ROOT / r["build_dockerfile"]).resolve()
                self.assertTrue(folder.is_dir())
                self.assertTrue(dockerfile.is_file())
                self.assertTrue(dockerfile.is_relative_to(folder))
                source = dockerfile.read_text(encoding="utf-8")
                self.assertNotRegex(source, PARENT_CONTEXT_COPY_RE)

    def test_parent_context_guard_rejects_real_dockerfile_syntax(self):
        for offending in (
            "COPY ../private.env /app/private.env",
            "   ADD  ../state /state",
            'COPY ["../outside", "/app/outside"]',
            "COPY --chown=1000:1000 ../internal /app/internal",
        ):
            with self.subTest(instruction=offending):
                self.assertRegex(offending, PARENT_CONTEXT_COPY_RE)
        for safe in (
            "COPY --from=builder /app/dist ./dist",
            "COPY src ./src",
            "ADD assets /app/assets",
        ):
            with self.subTest(instruction=safe):
                self.assertNotRegex(safe, PARENT_CONTEXT_COPY_RE)

    def test_exact_fifteen_source_ready_and_unreleased_coolify(self):
        approved = {
            "github-ops-mcp", "hermes-gateway", "multica-mcp",
            "repowise-deployment-publisher-staging", "emailens-mcp",
            "plasmic-mcp", "supabase-mcp", "ubuntu-mcp",
            "mantic-mcp", "playwright-mcp", "comfy-mcp",
            "coolify-mcp", "qdrant-mcp", "hindsight-mcp", "opik-mcp",
        }
        ready = {row["id"] for row in self.rows if row["source_build_ready"]}
        self.assertEqual(ready, approved)
        coolify = next(row for row in self.rows if row["id"] == "coolify-mcp")
        self.assertEqual(coolify["source_root"], "mcp/coolify-mcp")
        self.assertEqual(coolify["build_dockerfile"], "mcp/coolify-mcp/Dockerfile")
        # PR #221 source is now in main; production release parity remains unverified.
        self.assertTrue(coolify["source_build_ready"])

    def test_staging_compose_has_owned_context_without_mount_drift(self):
        """A safe staged migration never silently changes active Compose or host mounts."""
        folder = ROOT / "ops" / "repowise"
        active = (folder / "compose.publisher.coolify.yaml").read_text(encoding="utf-8")
        owned = (folder / "compose.publisher.owned.yaml").read_text(encoding="utf-8")
        self.assertIn("      context: ./ops/repowise", active.splitlines())
        self.assertIn("      context: .", owned.splitlines())
        self.assertNotIn("context: ./ops/repowise", owned)
        self.assertIn("      dockerfile: Dockerfile.publisher", owned)
        self.assertIn("base_directory=/ops/repowise", owned)
        self.assertIn("docker_compose_location=/compose.publisher.owned.yaml", owned)
        # The only Compose configuration difference is the relative build
        # context. This prevents unnoticed data/volume/auth changes at cutover.
        def non_comment_lines(text):
            return [line for line in text.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(non_comment_lines(owned),
                         non_comment_lines(active.replace(
                             "      context: ./ops/repowise", "      context: .")))
        self.assertTrue((folder / "Dockerfile.publisher").is_file())

    def test_missing_or_external_sources_are_never_marked_as_ready(self):
        for service in ("plasmic",):
            row = next(r for r in self.rows if r["id"] == service)
            self.assertFalse(row["source_build_ready"], service)
        self.assertTrue(next(r for r in self.rows if r["id"] == "github-ops-mcp")["source_build_ready"])
        self.assertTrue(next(r for r in self.rows if r["id"] == "multica-mcp")["source_build_ready"])

if __name__ == "__main__":
    unittest.main()
