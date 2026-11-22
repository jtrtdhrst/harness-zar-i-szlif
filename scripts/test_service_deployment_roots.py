import json
import re
import unittest
from pathlib import Path
from scripts.select_service_deployments import select
ROOT=Path(__file__).resolve().parent.parent
class TestOwnedComposeCandidates(unittest.TestCase):
    def test_exact_20_without_coolify_mcp(self):
        src=json.loads((ROOT/"ops/service-build-roots.json").read_text())
        manifest=json.loads((ROOT/"ops/service-deployment-roots.json").read_text())
        want={(r["id"],r["uuid"]) for r in src["resources"] if not r["source_build_ready"] and r["id"]!="coolify-mcp"}
        have={(r["id"],r["uuid"]) for r in manifest["resources"]}
        self.assertEqual(len(want),20)
        self.assertEqual(have,want)
    def test_fail_closed_and_owned_directories(self):
        manifest=json.loads((ROOT/"ops/service-deployment-roots.json").read_text())
        for row in manifest["resources"]:
            with self.subTest(id=row["id"]):
                root=(ROOT/row["root"]).resolve()
                self.assertTrue(root.is_relative_to(ROOT))
                self.assertTrue(root.is_dir())
                owned=root/"deploy/service-contract.json"
                self.assertEqual(json.loads(owned.read_text()),row)
                self.assertFalse(row["source_build_ready"])
                self.assertEqual(row["release_gate"],"HOLD")
                self.assertFalse(row["production_source_verified"])
                self.assertFalse(row["e2e_verified"])
                self.assertFalse(row["rollback_verified"])
                self.assertTrue(row["observed_images"])
                for im in row["observed_images"]:
                    self.assertFalse(im["release_digest_verified"])
                if row["versioned_compose"]:
                    f=(ROOT/row["versioned_compose"]).resolve()
                    self.assertTrue(f.is_relative_to(root))
                    data=f.read_text()
                    self.assertIn("NOT APPROVED FOR DEPLOYMENT",data)
                    refs = re.findall(r"(?m)^\s*image:\s*(.+)$", data)
                    self.assertTrue(refs)
                    for ref in refs:
                        self.assertRegex(ref,r"@sha256:[0-9a-f]{64}$")
    def test_exact_changes_only(self):
        self.assertEqual(select(["qdrant/anything"]),["qdrant"])
        self.assertEqual(select(["cloudflared-mcp/compose.yaml"]),["cloudflared-mcp"])
        self.assertEqual(select(["comfyui-mcp/src/foo.ts"]),["comfy","comfy-mcp"])
        self.assertEqual(select(["coolify-mcp/Dockerfile"]),[])
if __name__=="__main__":
    unittest.main()
