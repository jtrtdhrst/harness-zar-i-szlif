"""Regression checks for Coolify publisher admission in RepoWise GitHub sync."""
from pathlib import Path
import subprocess
import unittest

SOURCE = Path(__file__).with_name("repowise_github_sync.sh")

class CoolifyPublisherSyncContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_shell_syntax(self):
        subprocess.run(["bash", "-n", str(SOURCE)], check=True)

    def test_publisher_admission_is_fail_closed(self):
        s = self.source
        self.assertIn("label=coolify.resourceName=repowise-deployment-publisher-staging", s)
        self.assertIn("coolify.applicationUuid", s)
        self.assertIn("publisher_mount_or_rw_mismatch", s)
        self.assertIn("publisher_unexpected_mount_count", s)
        self.assertIn("SYNC_COOLIFY_PUBLISHER_INCLUDED", s)
        self.assertIn("CONSUMERS+=", s)
        self.assertLess(s.index("COOLIFY_PUBLISHERS"), s.index("prepare_live_sources\\ncheck_live_worktrees\\nstop_consumers".replace("\\n", "\n")))
        self.assertIn("--require-stopped", s)

if __name__ == "__main__":
    unittest.main()
