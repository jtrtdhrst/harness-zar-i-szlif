"""Prove the image catalog covers MCP services without conflating image IDs and production releases."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

class ImageCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=json.loads((ROOT/"ops/mcp-images/catalog.json").read_text())
        cls.registry=json.loads((ROOT/"ops/coolify-service-registry.json").read_text())

    def test_complete_unique_coolify_mcp_coverage(self):
        expected={x["uuid"] for x in self.registry["resources"]
                  if ("mcp" in x["name"].lower() or x["name"]=="hermes-gateway") and x.get("source") != "owned-image"}
        actual=[x["coolify_uuid"] for x in self.catalog["items"]]
        self.assertEqual(set(actual),expected)
        self.assertEqual(len(actual),len(set(actual)))

    def test_all_source_roots_exist_and_release_evidence_is_fail_closed(self):
        for x in self.catalog["items"]:
            with self.subTest(service=x["service"]):
                self.assertIsNone(x["verified_remote_oci_digest"])
                self.assertIsNone(x["verified_production_source_sha"])
                self.assertFalse(x["verified_production_e2e"])
                if x["source_root"]:
                    self.assertTrue((ROOT/x["source_root"]).is_dir())
                if x["dockerfile"]:
                    self.assertTrue((ROOT/x["dockerfile"]).is_file())
                for container in x["running_containers"]:
                    self.assertRegex(container["image_id"],r"^sha256:[a-f0-9]{64}$")
                if x["last_published_ghcr_tag"]:
                    self.assertRegex(x["last_published_ghcr_tag"],r"^ghcr.io/jtrtdhrst/harness-[a-z0-9-]+:sha-[a-f0-9]{40}$")

    def test_qdrant_source_matches_captured_live_bytes(self):
        x=next(x for x in self.catalog["items"] if x["service"]=="qdrant-mcp")
        self.assertEqual(x["dockerfile"],"mcp/qdrant-mcp/Dockerfile")
        self.assertEqual(hashlib.sha256((ROOT/"mcp/qdrant-mcp/server.py").read_bytes()).hexdigest(),
                         x["runtime_matching_server_sha256"])
        self.assertEqual(hashlib.sha256((ROOT/"mcp/qdrant-mcp/requirements.txt").read_bytes()).hexdigest(),
                         x["runtime_matching_requirements_sha256"])

if __name__=="__main__":
    unittest.main()
