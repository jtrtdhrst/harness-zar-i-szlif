"""Regression guard: source-only directories never trigger automatic Docker image builds.

The allowlist is intentionally narrow. MCP image tests may build on PRs,
non-MCP image jobs must be manual and run on the dedicated local runner.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
AUTO_MCP_IMAGE_WORKFLOWS = {"github-ops-mcp-ci.yml", "opik-mcp-access-guard.yml"}
# Reviewed inventory: deleting a workflow must require an explicit policy update.
EXPECTED_DOCKER_BUILD_JOBS = {
    ("github-ops-mcp-ci.yml", "verify"),
    ("hermes-gateway-image.yml", "validate-hermes-gateway-image"),
    ("hermes-paperclip-adapter-overlay.yml", "validate-and-publish"),
    ("opik-mcp-access-guard.yml", "jwt-regression"),
    ("paperclip-core-review-recovery.yml", "validate"),
    ("mcp-images-ghcr.yml", "build-and-push"),
    ("owned-runtime-images-ghcr.yml", "source-regressions"),
    ("owned-runtime-images-ghcr.yml", "publish"),
    ("source-build-roots-pr.yml", "verify-owned-source"),
    ("source-build-roots-pr.yml", "build-all-10-owned-sources"),
}
DOCKER_BUILD = re.compile(r"\bdocker\s+build\b|docker/build-push-action@|buildah\s+bud\b")

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
    if workflow_name == "source-build-roots-pr.yml":
        # Premerge source verification is disposable GitHub-hosted, read-only
        # to packages, and builds declared owned contexts only.
        if "    runs-on: ubuntu-latest" not in job:
            return False
        if any(token in job for token in (
                "docker push ", "packages: write", "/api/v1/deploy",
                "curl -X PATCH", "coolify deploy", "/var/run/docker.sock")):
            return False
        if "docker build --pull -f ops/repowise/Dockerfile.publisher" in job:
            return "ops/repowise" in job
        return ('-f "$ROOT/$DOCKERFILE" "$ROOT"' in job
                and 'test "$ROOT" != "."' in job
                and 'test "$ROOT" != "/"' in job
                and 'test "$(git rev-parse HEAD)" = "$SOURCE_SHA"' in job)
    if workflow_name == "owned-runtime-images-ghcr.yml":
        # Explicit review of the new OWNED path. PR Docker smoke is isolated
        # on a disposable GitHub-hosted runner with zero release permissions.
        # Main publication may push SHA-bound OCI artifacts, never deploy.
        forbidden = ("/api/v1/deploy", "curl -X PATCH", "coolify deploy",
                     "/var/run/docker.sock", "GITHUB_TOKEN: write")
        if any(needle in job for needle in forbidden):
            return False
        if "    if: github.event_name == 'pull_request'" in job:
            return ("    runs-on: ubuntu-latest" in job
                    and "docker build --pull -f integrations/hermes-paperclip/gateway/Dockerfile" in job
                    and "hermes-paperclip/gateway" in job
                    and "docker run --rm --network none" in job
                    and "docker push " not in job)
        return ("    if: github.ref == 'refs/heads/main'" in job
                and "    runs-on: ubuntu-latest" in job
                and "      packages: write" in job
                and "context: ./${{ matrix.directory }}" in job
                and "file: ./${{ matrix.dockerfile }}" in job
                and "docker/build-push-action@v6" in job
                and "push: true" in job
                and "test \"$GITHUB_REF\" = \"refs/heads/main\"" in job
                and "test \"$(git rev-parse HEAD)\" = \"$GITHUB_SHA\"" in job)
    if workflow_name == "mcp-images-ghcr.yml":
        # Trusted main builds inside a private rootless user namespace on the
        # existing local-build runner. The job must never reach a host or guest
        # Docker socket, and only the package-write job may push OCI artifacts
        # (this does NOT grant Coolify promotion).
        return ("    runs-on: [self-hosted, linux, x64, local-build]" in job
                and "      packages: write" in job
                and "buildah bud" in job
                and "buildah push" in job
                and "ghcr.io/" in job
                and "! test -w /var/run/docker.sock" in job
                and "! test -w /run/zis-ci-guest/docker.sock" in job)
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

    def test_mcp_image_workflow_uses_unprivileged_rootless_runner(self):
        text = (WORKFLOWS / "mcp-images-ghcr.yml").read_text(encoding="utf8")
        self.assertIn("runs-on: [self-hosted, linux, x64, local-build]", text)
        self.assertNotIn("runs-on: ubuntu-latest", text)
        self.assertIn("github.ref == 'refs/heads/main'", text)
        self.assertIn("      packages: write", text)
        self.assertIn("scripts/select_mcp_builds.py", text)
        # Protect SHA-bound package publication and prevent lost push events.
        self.assertNotIn("\nconcurrency:", text)
        pins = {"actions/checkout": "11d5960a326750d5838078e36cf38b85af677262"}
        for action, commit in pins.items():
            self.assertIn("uses: " + action + "@" + commit, text)
            self.assertNotRegex(text, r"uses: " + re.escape(action) + r"@v\d")
        # Rootless Buildah only: no privileged Docker actions, no host/guest socket.
        for forbidden in ("docker/setup-buildx-action", "docker/login-action",
                          "docker/build-push-action"):
            self.assertNotIn(forbidden, text)
        self.assertIn("buildah bud --isolation=chroot", text)
        self.assertIn("--digestfile", text)
        self.assertIn('test "$(id -un)" = actions-zis', text)
        self.assertIn("! test -w /var/run/docker.sock", text)
        self.assertIn("! test -w /run/zis-ci-guest/docker.sock", text)
        self.assertNotIn("curl -X PATCH", text)
        self.assertNotIn("/api/v1/deploy", text.lower())

    def test_premerge_owned_root_builds_are_hosted_and_bounded(self):
        workflow = (WORKFLOWS / "source-build-roots-pr.yml").read_text(encoding="utf8")
        jobs = dict(image_build_jobs(workflow))
        self.assertEqual(set(jobs), {"verify-owned-source", "build-all-10-owned-sources"})
        for job in jobs.values():
            self.assertTrue(compliant("source-build-roots-pr.yml", job))
            self.assertFalse(compliant("source-build-roots-pr.yml", job.replace(
                "runs-on: ubuntu-latest", "runs-on: [self-hosted, linux]")))
            self.assertFalse(compliant("source-build-roots-pr.yml", job + "\n      - run: docker push ghcr.io/something"))

    def test_owned_runtime_main_build_is_narrowly_allowed(self):
        workflow = (WORKFLOWS / "owned-runtime-images-ghcr.yml").read_text(encoding="utf8")
        jobs = dict(image_build_jobs(workflow))
        self.assertEqual(set(jobs), {"source-regressions", "publish"})
        self.assertTrue(compliant("owned-runtime-images-ghcr.yml", jobs["source-regressions"]))
        self.assertTrue(compliant("owned-runtime-images-ghcr.yml", jobs["publish"]))
        for mutated in (
            jobs["publish"].replace("refs/heads/main", "refs/heads/feature"),
            jobs["publish"].replace("context: ./${{ matrix.directory }}", "context: ."),
            jobs["publish"].replace("runs-on: ubuntu-latest", "runs-on: [self-hosted, linux]"),
            jobs["publish"].replace("test \"$(git rev-parse HEAD)\" = \"$GITHUB_SHA\"", "echo unchecked"),
        ):
            self.assertFalse(compliant("owned-runtime-images-ghcr.yml", mutated))
        self.assertFalse(compliant("ordinary-service.yml", jobs["publish"]))

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
