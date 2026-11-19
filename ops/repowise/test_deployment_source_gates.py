"""Offline check of the RepoWise generator's systemd sandbox and source inventory."""
from pathlib import Path
import unittest
import re

ROOT = Path(__file__).resolve().parents[2]

class GeneratorDeploymentTests(unittest.TestCase):
    def test_install_map_covers_every_host_helper_used_by_generator(self):
        manifest = (ROOT/"ops/repowise/README.md").read_text()
        mapping = dict(re.findall(r"\| `(ops/repowise/[^|]+?)` \| `(/opt/repowise-knowledge/[^|]+?)` \|", manifest))
        required = {
            "unwritten.py": "ops/repowise/repowise_unwritten.py",
            "refill-pages.sh": "ops/repowise/repowise_refill_pages.sh",
            "repowise_retire_orphan_flows.py": "ops/repowise/repowise_retire_orphan_flows.py",
        }
        src = (ROOT/"ops/repowise/repowise_refill_all.sh").read_text()
        for basename, repo_path in required.items():
            self.assertIn(f"$BASE/{basename}",src)
            self.assertEqual(mapping.get(repo_path),f"/opt/repowise-knowledge/{basename}")
            self.assertTrue((ROOT/repo_path).is_file())

    def test_generator_requires_fail_closed_host_sandbox(self):
        unit=(ROOT/"ops/systemd/repowise-generate.service").read_text()
        for mandatory in (
            "NoNewPrivileges=yes","PrivateTmp=yes","PrivateDevices=yes",
            "ProtectSystem=strict","ProtectKernelTunables=yes",
            "ProtectKernelModules=yes","ProtectControlGroups=yes",
            "RestrictSUIDSGID=yes","CapabilityBoundingSet=",
            "ReadWritePaths=/run/lock","RestrictAddressFamilies=AF_UNIX"
        ):
            self.assertIn(mandatory,unit)
        self.assertNotIn("ReadWritePaths=/var/run/docker.sock",unit)
        self.assertIn("User=root",unit)  # explicit legacy Docker socket risk, never disguised as rootless

if __name__=="__main__":
    unittest.main()
