"""Regression checks for Coolify publisher admission in RepoWise GitHub sync."""
from pathlib import Path
import json
import subprocess
import sys
import unittest

SOURCE = Path(__file__).with_name("repowise_github_sync.sh")
PRODUCT = "/var/lib/docker/volumes/oea9obpkhzbgkmipxwqmz2hj-repowise-workspace/_data/product"

def guard():
    script = SOURCE.read_text(encoding="utf-8")
    marker = 'docker inspect "$coolify_publisher" | python3 -c ' + "'\n"
    return script.split(marker, 1)[1].split("\n' || fail", 1)[0]

def fixture():
    def mount(dest, source, rw):
        return {"Destination": dest, "Source": source, "RW": rw}
    return {
        "Config": {
            "User": "999:999",
            "Labels": {
                "coolify.managed": "true",
                "coolify.projectName": "repowise-knowledge",
                "coolify.resourceName": "repowise-deployment-publisher-staging",
                "coolify.applicationUuid": "gl8bvfjtw2af8hkox4mguzzr",
            },
        },
        "HostConfig": {"ReadonlyRootfs": True, "NetworkMode": "host"},
        "Mounts": [
            mount("/workspace/product", PRODUCT, False),
            mount("/workspace/product/.repowise/episodes", PRODUCT + "/.repowise/episodes", True),
            mount("/run/lock/repowise-github-sync.lock", "/run/lock/repowise-github-sync.lock", False),
            mount("/run/secrets/repowise-token", "/etc/repowise-publisher/product.token", False),
        ],
    }

def check(payload):
    return subprocess.run(
        [sys.executable, "-c", guard()],
        input=json.dumps([payload]), text=True, capture_output=True
    )

class CoolifyPublisherSyncContractTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(["bash", "-n", str(SOURCE)], check=True)

    def test_positive_expected_isolation(self):
        result = check(fixture())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_negative_writable_product_mount(self):
        payload = fixture()
        payload["Mounts"][0]["RW"] = True
        result = check(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("publisher_mount_or_rw_mismatch", result.stderr)

    def test_negative_writable_token_mount(self):
        payload = fixture()
        payload["Mounts"][3]["RW"] = True
        self.assertIn("publisher_mount_or_rw_mismatch", check(payload).stderr)

    def test_negative_wrong_identity(self):
        payload = fixture()
        payload["Config"]["Labels"]["coolify.applicationUuid"] = "wrong"
        self.assertIn("publisher_identity_changed", check(payload).stderr)

    def test_negative_extra_mount(self):
        payload = fixture()
        payload["Mounts"].append({"Source": "/tmp", "Destination": "/extra", "RW": True})
        self.assertIn("publisher_unexpected_mount_count", check(payload).stderr)

    def test_order_precedes_swap_and_rollback(self):
        s = SOURCE.read_text(encoding="utf-8")
        self.assertIn("SYNC_COOLIFY_PUBLISHER_INCLUDED", s)
        self.assertLess(s.index("COOLIFY_PUBLISHERS"), s.index("prepare_live_sources\ncheck_live_worktrees\nstop_consumers"))
        self.assertIn("--require-stopped", s)

if __name__ == "__main__":
    unittest.main()
