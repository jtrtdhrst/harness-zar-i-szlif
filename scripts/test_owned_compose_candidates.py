"""Structural candidate controls, not production E2E or immutable image proof."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "ops" / "service-build-roots.json"
REGISTRY = ROOT / "ops" / "compose-migration-candidates.json"
IMAGE = re.compile(r"(?m)^\s*image:\s*(.+)$")
DIGEST = re.compile(r"@sha256:[a-f0-9]{64}\b")

class HarnessComposeCandidatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mapping = json.loads(MAP.read_text(encoding="utf-8"))["resources"]
        cls.rows = json.loads(REGISTRY.read_text(encoding="utf-8"))["resources"]

    def test_exact_three_uuid_ownership_no_coolify_mcp(self):
        source = {r["id"]: r for r in self.mapping
                  if not r["source_build_ready"] and r["id"] != "coolify-mcp"}
        self.assertEqual(len(source), 3)
        self.assertEqual(len(self.rows), 3)
        self.assertEqual({r["id"] for r in self.rows}, set(source))
        self.assertEqual(len({r["uuid"] for r in self.rows}), 3)
        for row in self.rows:
            self.assertEqual(row["uuid"], source[row["id"]]["uuid"])
            self.assertEqual(row["root"], source[row["id"]]["source_root"])
            self.assertFalse(row["release_ready"])
            self.assertFalse(source[row["id"]]["compose_release_ready"])

    def test_compose_candidates_refuse_false_source_builds_and_mutable_images(self):
        for row in self.rows:
            with self.subTest(resource=row["id"]):
                root = (ROOT / row["root"]).resolve()
                self.assertTrue(root.is_relative_to(ROOT))
                self.assertNotEqual(root, ROOT)
                self.assertTrue(root.is_dir())
                contract = json.loads((ROOT / row["contract"]).read_text())
                self.assertEqual(contract["uuid"], row["uuid"])
                self.assertEqual(contract["release_state"], "BLOCKED")
                self.assertFalse(contract["source_build_ready"])
                yaml = (ROOT / row["compose"]).read_text(encoding="utf-8")
                self.assertIn("services:", yaml)
                self.assertNotRegex(yaml, r"(?m)^\s*build:")
                self.assertNotRegex(yaml, r"(?m)^\s*context:\s*/(?:\s|$)")
                self.assertNotRegex(yaml, r"(?m)^\s*image:\s*.*(?::latest|:HEAD)(?:\s|$)")
                images = IMAGE.findall(yaml)
                self.assertGreater(len(images), 0)
                for image in images:
                    self.assertTrue(DIGEST.search(image) or
                                    ("PINNED_IMAGE_" in image and ":?" in image),
                                    (row["id"], image))
                self.assertNotRegex(yaml, r"ghp_|github_pat_|xoxb-|-----BEGIN PRIVATE KEY")

    def test_no_inline_database_credentials_in_any_candidate(self):
        # URL credentials must use the existing runtime secret variables.
        auth_uri = re.compile(
            r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|"
            r"redis(?:s)?|amqp(?:s)?|https?):\/\/[^:\s/@]+:([^@\s]+)@"
        )
        def literal_credential(line):
            match = auth_uri.search(line)
            return bool(match and "${" not in match.group(1)
                        and "$" not in match.group(1))
        self.assertTrue(literal_credential("DATABASE_URL: postgres://u:hardcoded@db:5432/x"))
        self.assertTrue(literal_credential("DATABASE_URL: https://u:hardcoded@example.test"))
        self.assertFalse(literal_credential(
            'DATABASE_URL: "postgres://u:${DB_PASSWORD}@db:5432/x"'))
        self.assertFalse(literal_credential("REDIS_URL: redis://redis:6379"))
        for row in self.rows:
            source = (ROOT / row["compose"]).read_text(encoding="utf-8")
            with self.subTest(resource=row["id"]):
                for lineno, line in enumerate(source.splitlines(), 1):
                    self.assertFalse(literal_credential(line),
                                     (row["id"], lineno, "inline authentication forbidden"))

    def test_select_exact_source_dependency_and_negative_cases(self):
        import select_owned_compose
        cases = {
            "qdrant/compose.candidate.yml": set(),
            "qdrant-extra/Dockerfile": set(),
            "mautic/release-contract.json": set(),
            "comfy-mcp/Dockerfile": set(),
            "ops/repowise/README.md": set(),
            "coolify-mcp/Dockerfile": set(),
            "docs/unrelated.md": set(),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(set(select_owned_compose.select([path])), expected)
        self.assertEqual(len(select_owned_compose.select(
            ["ops/compose-migration-candidates.json"])), 3)

if __name__ == "__main__":
    unittest.main()
