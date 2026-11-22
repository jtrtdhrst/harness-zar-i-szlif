"""Canonical source to Coolify catalog: preserve explicit owner and eliminate fake roots."""
import json
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
class SourceLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=json.loads((ROOT/"ops/coolify-service-registry.json").read_text())["resources"]
    def test_all_36_distinct_live_coolify_resources(self):
        self.assertEqual(len(self.rows),36)
        self.assertEqual(len({x["uuid"] for x in self.rows}),36)
        self.assertEqual(len({x["name"] for x in self.rows}),36)
        self.assertEqual(sum(x["type"]=="application" for x in self.rows),11)
        self.assertEqual(sum(x["type"]=="service" for x in self.rows),25)
    def test_source_owner_is_real_not_a_dummy_directory(self):
        no_root={"vendor-image","upstream-git","local-image-unknown-source","other-repository"}
        for x in self.rows:
            with self.subTest(name=x["name"]):
                if x["source"] in no_root:
                    self.assertNotIn("root",x)
                else:
                    self.assertTrue((ROOT/x["root"]).is_dir())
                if x.get("dockerfile"):
                    self.assertTrue((ROOT/x["dockerfile"]).is_file())
        for removed in ("cloudflare-ingress","cloudflared-mcp","local-build-registry",
                        "mcp-activation","outline-knowledge","shared-ingress","supabase",
                        "repowise-mcp-runtime","comfyui-mcp"):
            self.assertFalse((ROOT/removed).exists(),removed)
    def test_service_folder_matches_owned_mcp_source(self):
        for name in ("playwright-mcp","mantic-mcp","comfy-mcp","multica-mcp",
                     "plasmic-mcp","emailens-mcp","ubuntu-mcp","supabase-mcp"):
            r=next(x for x in self.rows if x["name"]==name)
            self.assertEqual(r["root"],name)
            self.assertEqual(r["source"],"owned-code")
            self.assertTrue((ROOT/r["dockerfile"]).is_file())
    def test_unmerged_prs_not_claimed_as_main_source(self):
        for name in ("qdrant-mcp","coolify-mcp","hindsight-mcp"):
            r=next(x for x in self.rows if x["name"]==name)
            self.assertEqual(r["source"],"source-pending")
            self.assertNotIn("dockerfile",r)
if __name__=="__main__":
    unittest.main()
