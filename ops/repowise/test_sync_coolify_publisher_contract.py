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
    marker = 'docker inspect --format "$INSPECT_FORMAT" "$coolify_publisher" | python3 -c ' + "'\n"
    return script.split(marker, 1)[1].split("\n' || fail", 1)[0]

def discover(payloads):
    script = SOURCE.read_text(encoding="utf-8")
    marker = 'COOLIFY_PUBLISHER=$(python3 -c ' + "'\n"
    discovery = script.split(marker, 1)[1].split("\n' <<< \"$ALL_RUNNING_INSPECT\")", 1)[0]
    return subprocess.run([sys.executable, "-c", discovery],
                          input="\n".join(json.dumps(x) for x in payloads), text=True, capture_output=True)

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
        input=json.dumps(payload), text=True, capture_output=True
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

    def test_discovery_expected_identity(self):
        payload = fixture()
        payload["Name"] = "/publisher-gl8bvfjtw2af8hkox4mguzzr-20261118"
        result = discover([payload])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("publisher-gl8bvfjtw2af8hkox4mguzzr-20261118", result.stdout)

    def test_discovery_changed_resource_label_still_selects_candidate(self):
        payload = fixture()
        payload["Name"] = "/publisher-gl8bvfjtw2af8hkox4mguzzr-20261118"
        payload["Config"]["Labels"]["coolify.resourceName"] = "renamed-resource"
        result = discover([payload])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("publisher-gl8bvfjtw2af8hkox4mguzzr", result.stdout)
        self.assertIn("publisher_identity_changed", check(payload).stderr)

    def test_discovery_changed_all_labels_but_product_mount_remains_visible(self):
        payload = fixture()
        payload["Name"] = "/publisher-gl8bvfjtw2af8hkox4mguzzr-20261118"
        payload["Config"]["Labels"] = {}
        result = discover([payload])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("publisher-gl8bvfjtw2af8hkox4mguzzr", result.stdout)
        self.assertIn("publisher_identity_changed", check(payload).stderr)

    def test_discovery_no_publisher_fails_closed(self):
        self.assertNotEqual(discover([{"Name":"/unrelated","Mounts":[],"Config":{"Labels":{}}}]).returncode, 0)

    def test_discovery_two_candidates_fails_closed(self):
        payload = fixture()
        payload["Name"] = "/publisher-a"
        another = fixture()
        another["Name"] = "/publisher-b"
        self.assertIn("publisher_discovery_expected_exactly_one_got_2", discover([payload, another]).stderr)

    def test_source_detects_docker_list_and_inspect_failures(self):
        s = SOURCE.read_text(encoding="utf-8")
        self.assertIn('RUNNING_IDS=$(docker ps --quiet) || fail "coolify-docker-list-failed"', s)
        self.assertIn('ALL_RUNNING_INSPECT=$(docker inspect --format "$INSPECT_FORMAT" $RUNNING_IDS) || fail "coolify-docker-inspect-failed"', s)
        self.assertIn('|| fail "coolify-publisher-discovery-failed"', s)

    def test_inspect_projection_never_reads_environment_values(self):
        s = SOURCE.read_text(encoding="utf-8")
        projection = s.split("INSPECT_FORMAT='",1)[1].split("'\nALL_RUNNING_INSPECT=",1)[0]
        self.assertNotIn(".Config.Env", projection)
        self.assertNotIn('"Env"', projection)
        self.assertNotIn("{{json .Config}}", projection)
        self.assertIn("{{json .Config.User}}", projection)
        self.assertIn("{{json .Mounts}}", projection) if "{{json .Mounts}}" in projection else self.assertIn(".Mounts",projection)
        self.assertIn("coolify.applicationUuid", projection)
        self.assertIn('docker inspect --format "$INSPECT_FORMAT" "$coolify_publisher"', s)
        self.assertIn('docker inspect --format "$INSPECT_FORMAT" $RUNNING_IDS', s)

    def test_order_precedes_swap_and_rollback(self):
        s = SOURCE.read_text(encoding="utf-8")
        self.assertIn("SYNC_COOLIFY_PUBLISHER_INCLUDED", s)
        self.assertLess(s.index("COOLIFY_PUBLISHERS"), s.index("prepare_live_sources\ncheck_live_worktrees\nstop_consumers"))
        self.assertIn("--require-stopped", s)

if __name__ == "__main__":
    unittest.main()
