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
    ("coolify-mcp-ci.yml", "verify"),
    ("coolify-mcp-ci.yml", "publish"),
    ("owned-runtime-images-ghcr.yml", "source-regressions"),
    ("owned-runtime-images-ghcr.yml", "publish"),
    ("source-build-roots-pr.yml", "verify-owned-source"),
    ("source-build-roots-pr.yml", "build-all-15-owned-sources"),
    ("vendor-repowise-source.yml", "verify-immutable-source-and-build"),
    ("vendor-repowise-source.yml", "publish-reviewed-main-image"),
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
    if workflow_name == "vendor-repowise-source.yml":
        # Narrow, audited exception: exact vendored RepoWise app source, NOT
        # arbitrary non-MCP builds. PR may smoke-build only on a disposable
        # GitHub runner; trusted main may publish immutable OCI by SHA.
        # Neither job is authorized to deploy to Coolify.
        forbidden = (
            "self-hosted", "/var/run/docker.sock", "/api/v1/deploy",
            "curl -X PATCH", "curl -X POST", "coolify deploy",
            "git push ", "docker push ", ":latest", "tags: latest",
        )
        if any(item.lower() in job.lower() for item in forbidden):
            return False
        if "    if: github.event_name == 'pull_request'" in job:
            required = (
                "    runs-on: ubuntu-latest",
                "      contents: read",
                "actions/checkout@v4",
                "persist-credentials: false",
                "python3 -m unittest discover -s scripts -p test_repowise_app_source.py",
                "docker build --pull --progress=plain -f apps/repowise/docker/Dockerfile",
                "-t repowise-zari-286-ci:${{ github.sha }} apps/repowise",
                "docker run --rm --entrypoint repowise",
            )
            return (all(value in job for value in required)
                    and "packages: write" not in job
                    and "id-token: write" not in job
                    and "attestations: write" not in job
                    and "docker/build-push-action@" not in job)
        main_guard = ("    if: github.repository == 'jtrtdhrst/harness-zar-i-szlif'"
                      " && github.event_name == 'push'"
                      " && github.ref == 'refs/heads/main'")
        required = (
            main_guard,
            "    runs-on: ubuntu-latest",
            "      contents: read",
            "      packages: write",
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "persist-credentials: false",
            "test \"$GITHUB_REPOSITORY\" = 'jtrtdhrst/harness-zar-i-szlif'",
            "test \"$GITHUB_REF\" = 'refs/heads/main'",
            'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
            "test \"$(git rev-parse HEAD:apps/repowise)\" = 'fe223cb9efd9ed04583522b132089c4770c66ea0'",
            "python3 -m unittest discover -s scripts -p test_repowise_app_source.py",
            "context: ./apps/repowise",
            "file: ./apps/repowise/docker/Dockerfile",
            "docker/build-push-action@v6",
            "push: true",
            "org.opencontainers.image.source=https://github.com/jtrtdhrst/harness-zar-i-szlif",
            "org.opencontainers.image.revision=${{ github.sha }}",
            "DIGEST: ${{ steps.image.outputs.digest }}",
            '[[ "$DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]',
            "Production promotion: NOT AUTHORIZED",
        )
        expected_tag = "ghcr.io/jtrtdhrst/harness-repowise:sha-${{ github.sha }}"
        tags = re.findall(r"(?m)^\s+tags: (.+)$", job)
        return (all(value in job for value in required)
                and tags == [expected_tag]
                and job.count("docker/build-push-action@") == 1
                and "docker build --pull" not in job
                and "      - uses: docker/login-action@v3" in job
                and "password: ${{ secrets.GITHUB_TOKEN }}" in job)
    if workflow_name == "coolify-mcp-ci.yml":
        # PR Docker smoke is allowed only for this service, on a disposable
        # hosted runner with pull-request-only steps and no release privileges.
        # Publishing remains a separate exact-main SHA-bound job.
        if "docker build --tag coolify-mcp:ci ./mcp/coolify-mcp" in job:
            forbidden = (
                "self-hosted", "/var/run/docker.sock", "/api/v1/deploy",
                "curl -X PATCH", "curl -X POST", "coolify deploy",
                "docker push ", "packages: write", "id-token: write",
                "attestations: write", "docker/build-push-action@",
            )
            if any(item.lower() in job.lower() for item in forbidden):
                return False
            required = (
                "    runs-on: ubuntu-latest",
                "docker build --tag coolify-mcp:ci ./mcp/coolify-mcp",
                "if: github.event_name == 'pull_request'",
                "docker image inspect --format '{{json .Config.Volumes}}' coolify-mcp:ci",
                "docker run --rm --network none --volume \"$volume:/data\"",
                "--env MCP_OAUTH_STATE_FILE=/data/oauth-state.json",
                "docker run --detach --network none --name \"$container\"",
                "docker exec \"$container\" node -e",
            )
            return (all(value in job for value in required)
                    and job.count("if: github.event_name == 'pull_request'") == 2)
        # Trusted main publication is SHA-bound to mcp/coolify-mcp/ alone.
        required = (
            "    if: github.event_name == 'push' && github.ref == 'refs/heads/main'",
            "    runs-on: ubuntu-latest",
            "      packages: write",
            "      - uses: docker/build-push-action@",
            "          context: ./mcp/coolify-mcp",
            "          file: ./mcp/coolify-mcp/Dockerfile",
            "          push: true",
            "          tags: ghcr.io/${{ github.repository_owner }}/coolify-mcp:sha-${{ github.sha }}",
            "          org.opencontainers.image.revision=${{ github.sha }}",
            "      - name: Verify immutable GHCR digest and exact trusted source",
            'test "$GITHUB_REF" = "refs/heads/main"',
            'test "$SOURCE_REPO" = "jtrtdhrst/harness-zar-i-szlif"',
            'test "$(git rev-parse HEAD)" = "$SOURCE_SHA"',
            "      - name: Attest SHA-bound OCI image provenance",
        )
        return (all(value in job for value in required)
                and "! test -w /var/run/docker.sock" not in job
                and "self-hosted" not in job
                and "/api/v1/deploy" not in job.lower()
                and "curl -X PATCH" not in job)
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

    def test_coolify_mcp_pr_image_smoke_is_readonly_and_path_scoped(self):
        source = (WORKFLOWS / "coolify-mcp-ci.yml").read_text(encoding="utf8")
        header = source.split("\\njobs:\\n", 1)[0]
        jobs = dict(image_build_jobs(source))
        verify = jobs["verify"]
        self.assertTrue(compliant("coolify-mcp-ci.yml", verify))
        self.assertIn("permissions:\\n  contents: read", header)
        self.assertNotIn("packages: write", header)
        for original, replacement in (
            ("if: github.event_name == 'pull_request'", "if: github.event_name == 'push'"),
            ("docker build --tag coolify-mcp:ci ./mcp/coolify-mcp", "docker build --tag other:ci ."),
            ("--network none", ""),
        ):
            self.assertFalse(
                compliant("coolify-mcp-ci.yml", verify.replace(original, replacement, 1)),
                f"unsafe Coolify MCP PR smoke mutation accepted: {original}",
            )

    def test_coolify_mcp_publisher_is_exact_main_only_and_source_scoped(self):
        source = (WORKFLOWS / "coolify-mcp-ci.yml").read_text(encoding="utf8")
        jobs = dict(image_build_jobs(source))
        publish = jobs["publish"]
        self.assertTrue(compliant("coolify-mcp-ci.yml", publish))
        for original in (
            "github.event_name == 'push'",
            "github.ref == 'refs/heads/main'",
            "    runs-on: ubuntu-latest",
            "      packages: write",
            "          context: ./mcp/coolify-mcp",
            "          file: ./mcp/coolify-mcp/Dockerfile",
            "          push: true",
            "          org.opencontainers.image.revision=${{ github.sha }}",
            'test "$SOURCE_REPO" = "jtrtdhrst/harness-zar-i-szlif"',
            'test "$(git rev-parse HEAD)" = "$SOURCE_SHA"',
            "      - name: Attest SHA-bound OCI image provenance",
        ):
            self.assertIn(original, publish)
            self.assertFalse(compliant("coolify-mcp-ci.yml", publish.replace(original, "REMOVED", 1)),
                             f"policy silently allows removal of {original!r}")
        for forbidden in ("self-hosted", "/api/v1/deploy", "curl -X PATCH"):
            self.assertFalse(compliant("coolify-mcp-ci.yml", publish + "\n" + forbidden))

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
        self.assertEqual(set(jobs), {"verify-owned-source", "build-all-15-owned-sources"})
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

    def test_repowise_vendor_ci_is_sha_bound_and_cannot_deploy(self):
        workflow = (WORKFLOWS / "vendor-repowise-source.yml").read_text(encoding="utf8")
        jobs = dict(image_build_jobs(workflow))
        self.assertEqual(
            set(jobs),
            {"verify-immutable-source-and-build", "publish-reviewed-main-image"},
        )
        smoke, publisher = (jobs["verify-immutable-source-and-build"],
                            jobs["publish-reviewed-main-image"])
        self.assertTrue(compliant("vendor-repowise-source.yml", smoke))
        self.assertTrue(compliant("vendor-repowise-source.yml", publisher))
        for original, replacement in (
            ("github.event_name == 'pull_request'", "github.event_name == 'push'"),
            ("runs-on: ubuntu-latest", "runs-on: [self-hosted, linux]"),
            ("persist-credentials: false", "persist-credentials: true"),
            ("apps/repowise/docker/Dockerfile", "Dockerfile"),
        ):
            self.assertFalse(compliant(
                "vendor-repowise-source.yml", smoke.replace(original, replacement, 1)
            ), f"unsafe PR smoke mutation accepted: {original}")
        for injected in ("packages: write", "docker push ghcr.io/other",
                         "curl -X POST https://host/api/v1/deploy"):
            self.assertFalse(compliant("vendor-repowise-source.yml", smoke + "\n" + injected))
        for original, replacement in (
            ("github.event_name == 'push'", "github.event_name == 'pull_request'"),
            ("refs/heads/main", "refs/heads/feature"),
            ("runs-on: ubuntu-latest", "runs-on: [self-hosted, linux]"),
            ("push: true", "push: false"),
            ("org.opencontainers.image.revision=${{ github.sha }}", "org.opencontainers.image.revision=latest"),
            ("test \"$(git rev-parse HEAD)\" = \"$GITHUB_SHA\"", "echo source-not-verified"),
            ("tags: ghcr.io/jtrtdhrst/harness-repowise:sha-${{ github.sha }}",
             "tags: ghcr.io/jtrtdhrst/harness-repowise:latest"),
        ):
            self.assertFalse(compliant(
                "vendor-repowise-source.yml", publisher.replace(original, replacement, 1)
            ), f"unsafe trusted-main mutation accepted: {original}")
        for injected in (
            "          tags: ghcr.io/jtrtdhrst/harness-repowise:latest",
            "curl -X PATCH https://host/api/v1/deploy",
            "docker push ghcr.io/other",
        ):
            self.assertFalse(compliant("vendor-repowise-source.yml", publisher + "\n" + injected))
        self.assertFalse(compliant("ordinary-service.yml", publisher))

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
