"""Regression guard: source-only directories never trigger automatic Docker image builds.

The allowlist is intentionally narrow. MCP image tests may build on PRs,
non-MCP image jobs must be manual and run on the dedicated local runner.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
AUTO_MCP_IMAGE_WORKFLOWS = {"opik-mcp-access-guard.yml"}
# Reviewed inventory: deleting a workflow must require an explicit policy update.
EXPECTED_DOCKER_BUILD_JOBS = {
    ("hermes-gateway-image.yml", "validate-hermes-gateway-image"),
    ("hermes-paperclip-adapter-overlay.yml", "validate-and-publish"),
    ("opik-mcp-access-guard.yml", "jwt-regression"),
    ("paperclip-core-review-recovery.yml", "validate"),
    ("mcp-images-ghcr.yml", "build-and-push"),
}
DOCKER_BUILD = re.compile(r"\bdocker\s+build\b|docker/build-push-action@")

def image_build_jobs(content):
    if "\njobs:\n" not in "\n" + content:
        return []
    segment = ("\n" + content).split("\njobs:\n", 1)[1]
    jobs, current, lines = [], None, []
    for line in segment.splitlines():
        match = re.match(r"^  ([A-Za-z][A-Za-z0-9_-]*):\s*$", line)
        if match:
            if current is not None and DOCKER_BUILD.search("\n".join(lines)):
                jobs.append((current, "\n".join(lines)))
            current, lines = match.group(1), []
        elif current is not None:
            lines.append(line)
    if current is not None and DOCKER_BUILD.search("\n".join(lines)):
        jobs.append((current, "\n".join(lines)))
    return jobs

def compliant(workflow_name, job):
    if workflow_name in AUTO_MCP_IMAGE_WORKFLOWS:
        return True
    if workflow_name == "mcp-images-ghcr.yml":
        # Docker executes on disposable GitHub-hosted workers, never on the
        # persistent local-build runner; only the job with package-write access
        # may push OCI artifacts (this does NOT grant Coolify promotion).
        return ("    runs-on: ubuntu-latest" in job
                and "      packages: write" in job
                and "docker/build-push-action@v6" in job
                and "ghcr.io/" in job)
    return (re.search(r"(?m)^    if: .*workflow_dispatch.*refs/heads/main", job) is not None
            and re.search(r"(?m)^    runs-on: \[self-hosted,.*local-build.*\]", job) is not None)

class NonMcpBuildGuardTests(unittest.TestCase):
    def test_no_automatic_builds_from_non_mcp_sources(self):
        observed = set()
        for workflow in sorted(WORKFLOWS.glob("*.yml")):
            for job_name, block in image_build_jobs(workflow.read_text(encoding="utf8")):
                observed.add((workflow.name, job_name))
                self.assertTrue(compliant(workflow.name, block),
                                f"{workflow.name}/{job_name} can build outside local manual release")
        self.assertEqual(observed, EXPECTED_DOCKER_BUILD_JOBS,
                         "Docker build workflow inventory changed without explicit review")

    def test_mcp_image_workflow_uses_unprivileged_ephemeral_runner(self):
        text = (WORKFLOWS / "mcp-images-ghcr.yml").read_text(encoding="utf8")
        self.assertIn("    runs-on: ubuntu-latest", text)
        self.assertNotIn("runs-on: [self-hosted", text)
        self.assertIn("github.ref == 'refs/heads/main'", text)
        self.assertIn("      packages: write", text)
        self.assertIn("scripts/select_mcp_builds.py", text)
        self.assertNotIn("curl -X PATCH", text)
        self.assertNotIn("coolify", text.lower())

    def test_retired_paperclip_mcp_ci_stays_absent(self):
        self.assertFalse((WORKFLOWS / "paperclip-mcp-ci.yml").exists(),
                         "Paperclip MCP CI must not re-enter the Multica pipeline")

    def test_new_non_mcp_workflow_build_is_rejected(self):
        automatic = "jobs:\n  accidental:\n    runs-on: ubuntu-latest\n    steps:\n      - run: docker build .\n"
        blocks = image_build_jobs(automatic)
        self.assertEqual(len(blocks), 1)
        self.assertFalse(compliant("ordinary-service.yml", blocks[0][1]))

    def test_manual_local_build_accepted(self):
        manual = ("jobs:\n  publish:\n"
                  "    if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'\n"
                  "    runs-on: [self-hosted, linux, x64, local-build]\n"
                  "    steps:\n      - uses: docker/build-push-action@v6\n")
        blocks = image_build_jobs(manual)
        self.assertEqual(len(blocks), 1)
        self.assertTrue(compliant("ordinary-service.yml", blocks[0][1]))

if __name__ == "__main__":
    unittest.main()
