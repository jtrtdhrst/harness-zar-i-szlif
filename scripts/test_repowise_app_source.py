"""Fail-closed provenance check for the complete vendored RepoWise app source."""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "ops/repowise/repowise-app-source.json"

class RepoWiseAppSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = json.loads(META.read_text(encoding="utf-8"))

    def test_pin_and_context(self):
        x = self.meta
        self.assertEqual(x["upstream_repository"], "repowise-dev/repowise")
        self.assertEqual(x["upstream_version"], "v0.60.1")
        self.assertEqual(x["upstream_commit"], "7ccd63f1b97d4f9f15dd79f930233f75e66d3e94")
        self.assertEqual(x["source_root"], "apps/repowise")
        self.assertEqual(x["dockerfile"], "apps/repowise/docker/Dockerfile")
        self.assertEqual(x["license"], "AGPL-3.0-or-later")
        self.assertEqual(x["coolify_application_uuid"], "oea9obpkhzbgkmipxwqmz2hj")
        self.assertTrue((ROOT/x["source_root"]).is_dir())
        self.assertTrue((ROOT/x["dockerfile"]).is_file())
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", (ROOT/x["source_root"]/"LICENSE").read_text())

    def test_all_tracked_upstream_files_are_imported_with_identical_git_tree(self):
        x = self.meta
        sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD:" + x["source_root"]], text=True).strip()
        self.assertEqual(x["upstream_git_tree"], "fe223cb9efd9ed04583522b132089c4770c66ea0")
        self.assertEqual(sha, x["upstream_git_tree"])
        paths = subprocess.check_output(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", "HEAD", x["source_root"]], text=True).splitlines()
        self.assertEqual(len(paths), x["upstream_tracked_file_count"])
        self.assertNotIn(x["source_root"] + "/.git", paths)

    def test_no_production_release_claim(self):
        self.assertEqual(self.meta["status"], "LOCAL_PRE_RELEASE_ONLY")
        self.assertTrue(self.meta["inventory_reconciliation_required_before_cutover"])
        self.assertEqual(self.meta["live_inventory_source_during_transition"], "upstream-git")
        self.assertIn("registry_and_build_roots_reconciled_to_actual_cutover", self.meta["requires_before_cutover"])
        self.assertIn("independent_exact_sha_code_review",self.meta["requires_before_cutover"])
        self.assertIn("live_positive_negative_e2e",self.meta["requires_before_cutover"])

if __name__ == "__main__":
    unittest.main()
