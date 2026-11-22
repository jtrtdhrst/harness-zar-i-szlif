"""Fail-closed structural inventory of all Harness Coolify build roots.

This is only a source-layout assertion, not image build / release proof.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "ops" / "service-build-roots.json"

class HarnessBuildRootsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.rows = cls.data["resources"]

    def test_exactly_all_31_coolify_harness_resources(self):
        self.assertEqual(self.data["schema_version"], 1)
        self.assertEqual(self.data["repo"], "jtrtdhrst/harness-zar-i-szlif")
        self.assertEqual(len(self.rows), 31)
        self.assertEqual(len({r["id"] for r in self.rows}), 31)
        self.assertEqual(len({r["uuid"] for r in self.rows}), 31)

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
                self.assertNotRegex(source, r"(?m)^\\s*(?:ADD|COPY)\\s+[^\\n]*\\.\\./")

    def test_missing_or_external_sources_are_never_marked_as_ready(self):
        for service in ("coolify-mcp", "qdrant-mcp", "hindsight-mcp", "comfy-mcp",
                        "opencode", "plasmic", "multica-stack"):
            row = next(r for r in self.rows if r["id"] == service)
            self.assertFalse(row["source_build_ready"], service)
        self.assertTrue(next(r for r in self.rows if r["id"] == "github-ops-mcp")["source_build_ready"])
        self.assertTrue(next(r for r in self.rows if r["id"] == "multica-mcp")["source_build_ready"])

if __name__ == "__main__":
    unittest.main()
