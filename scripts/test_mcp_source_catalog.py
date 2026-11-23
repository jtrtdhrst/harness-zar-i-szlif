"""Canonical source to Coolify catalog: preserve explicit owner and eliminate fake roots."""
import json
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
class SourceLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=json.loads((ROOT/"ops/coolify-service-registry.json").read_text())["resources"]
    def test_all_38_distinct_live_coolify_resources(self):
        self.assertEqual(len(self.rows),38)
        self.assertEqual(len({x["uuid"] for x in self.rows}),36)
        self.assertEqual(len({x["name"] for x in self.rows}),36)
        self.assertEqual(sum(x["type"]=="application" for x in self.rows),13)
        self.assertEqual(sum(x["type"]=="service" for x in self.rows),25)
    def test_source_owner_is_real_not_a_dummy_directory(self):
        no_root={"vendor-image","upstream-git","local-image-unknown-source","other-repository","owned-image"}
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
    def test_github_ops_canaries_reuse_owned_source_without_phantom_root(self):
        canaries = [x for x in self.rows if x["source"] == "owned-image"]
        self.assertEqual({x["name"] for x in canaries}, {
            "github-ops-mcp-digest-canary-a4a2f9b",
            "github-ops-mcp-immutable-prod-d17e135",
        })
        for entry in canaries:
            self.assertEqual(entry["origin_service"], "github-ops-mcp")
            self.assertEqual(entry["origin_root"], "mcp/github-mcp")
            self.assertEqual(entry["source_repository"], "jtrtdhrst/harness-zar-i-szlif")
            self.assertEqual(entry["build_pack"], "dockerimage")
            self.assertNotIn("root", entry)
    def test_service_folder_matches_owned_mcp_source(self):
        for name in ("playwright-mcp","mantic-mcp","comfy-mcp","multica-mcp",
                     "qdrant-mcp","coolify-mcp","hindsight-mcp","opik-mcp",
                     "plasmic-mcp","emailens-mcp","ubuntu-mcp","supabase-mcp"):
            r=next(x for x in self.rows if x["name"]==name)
            self.assertEqual(r["root"],"mcp/"+name)
            self.assertEqual(r["source"],"owned-code")
            self.assertTrue((ROOT/r["dockerfile"]).is_file())
    def test_unmerged_prs_not_claimed_as_main_source(self):
        for name in ():
            r=next(x for x in self.rows if x["name"]==name)
            self.assertEqual(r["source"],"owned-code")
            self.assertNotIn("dockerfile",r)
if __name__=="__main__":
    unittest.main()
