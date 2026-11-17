"""Fail-closed tests for the admission-gated Harness image delivery (ZARI-240).

The delivery module mirrors the audited installed controller's transport. These
tests exercise the wiring: the build stage requires ``evaluate_build``, the
deploy stage goes through ``run_promotion`` (full ``evaluate``), and the deploy
transport only ever resolves an already-prepared digest. Every denial in the
owner's list - held lane, missing/expired/stale attestation, mismatched SHA,
unauthorized UUID, unreviewed main merge - must produce zero docker build, zero
push, zero deploy and an unchanged running image.
"""
import base64
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import harness_delivery_controller as controller
import harness_native_delivery as delivery
import harness_release_admission as gate
from harness_release_admission import Denied, evaluate_build

NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
SOURCE = "a" * 40
HEAD = "b" * 40
DIGEST = "sha256:" + "c" * 64
PREVIOUS = "sha256:" + "9" * 64
UUID = "bioufw4uxwuhmr51ueyahf0u"
COMPOSE = """services:
  mantic:
    image: local/mantic-mcp:old
    ports:
      - 8080:8080
"""


def manifest(promotion_state="hold"):
    entry = {"id": "mantic-mcp", "platform": "coolify", "coolify_kind": "service",
             "coolify_uuid": UUID, "review_required": True, "exact_sha_required": True,
             "reviewer_role": "CHO", "reviewer_agent_id": "reviewer-agent"}
    if promotion_state:
        entry["promotion_state"] = promotion_state
    return {"schema_version": 1, "owner": "CHO", "lanes": [], "other_resources": [entry],
            "cloudflare_workers": []}


def request(**overrides):
    base = {"service": "mantic-mcp", "coolify_uuid": UUID, "coolify_kind": "service",
            "pr": 112, "base_ref": "main", "head_sha": HEAD, "source_sha": SOURCE,
            "merge_sha": SOURCE, "image_digest": DIGEST,
            "approval": {"reviewer_role": "CHO", "reviewer_agent_id": "reviewer-agent",
                         "producer_agent_id": "producer-agent", "approved_sha": HEAD}}
    base.update(overrides)
    return base


def grant(**overrides):
    base = {"schema_version": 1, "revoked": False, "coolify_uuid": UUID, "service": "mantic-mcp",
            "source_sha": SOURCE, "grant_id": "grant-1", "granted_by": "owner",
            "expires_at": (NOW + timedelta(hours=4)).isoformat()}
    base.update(overrides)
    return base


def attestation(**overrides):
    base = {"schema_version": 1, "signature_verified": True, "attestor_uid": 0, "runner_uid": 1000,
            "policy_digest": "sha256:" + "e" * 64, "service": "mantic-mcp", "source_sha": SOURCE,
            "image_digest": DIGEST, "tests": [{"command": "true", "exit": 0}],
            "changed_paths": ["mantic-mcp/src/server.ts"],
            "artifact_manifest_digest": "sha256:" + "d" * 64}
    base.update(overrides)
    # Only an attestation verified against real key material is admitted; the
    # fixture models that outcome, exactly like load_artifacts does.
    return gate.VerifiedAttestation(base)


class FakeHost:
    """Records every host mutation; models one Coolify service and its image."""

    def __init__(self, compose=COMPOSE, service_status="running:healthy",
                 container_status="Up 2 minutes (healthy)", revision=SOURCE,
                 images=None, probe="200"):
        self.calls = []
        self.compose = compose
        self.service_status = service_status
        self.container_status = container_status
        self.revision = revision
        self.images = dict(images or {})
        self.probe_result = probe

    # --- docker -----------------------------------------------------------
    def docker(self, *args, timeout=3600):
        self.calls.append(("docker",) + args)
        if args[0] == "image" and args[1] == "inspect":
            fmt = args[3] if len(args) > 3 else ""
            reference = args[-1]
            if "{{.Id}}" in fmt:
                return "sha256:imageid"
            if "RepoDigests" in fmt:
                known = self.images.get(reference)
                if known is None:
                    known = reference.split("@")[1] if "@" in reference else PREVIOUS
                return reference.split("@")[0] + "@" + known
            if "Labels" in fmt:
                return self.revision
        if args[0] == "ps":
            return self.container_status
        if args[0] == "push":
            return ""
        raise AssertionError(f"unexpected docker call {args}")

    def docker_build(self, argv, log_path):
        self.calls.append(("build",) + tuple(argv))
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text("built\n", encoding="utf-8")

    # --- coolify ----------------------------------------------------------
    def coolify(self, method, path, body=None):
        self.calls.append(("coolify", method, path))
        if method == "GET" and path.startswith("/services/"):
            return 200, {"docker_compose_raw": self.compose, "status": self.service_status}
        if method == "PATCH":
            self.compose = base64.b64decode(body["docker_compose_raw"]).decode()
            return 200, {}
        if method == "POST" and path == "/deploy":
            return 200, {"deployment_uuid": "dep-1"}
        raise AssertionError(f"unexpected coolify call {method} {path}")

    def probe(self, url):
        self.calls.append(("probe", url))
        return self.probe_result

    # --- assertions -------------------------------------------------------
    def mutations(self):
        return [call for call in self.calls
                if call[0] == "build" or (call[0] == "docker" and call[1] == "push")
                or (call[0] == "coolify" and call[1] in ("PATCH", "POST"))]


def transport_for(host):
    return delivery.Transport(host)


class BuildStageTests(unittest.TestCase):
    """`--mode prepare`: evaluate_build gates docker build and push."""

    def prepare(self, host, **kwargs):
        bundle = kwargs.pop("bundle", None) or {"request": request(), "grant": grant()}
        with patch.object(delivery, "STATE_ROOT", Path(tempfile.mkdtemp())):
            return evaluate_build(kwargs.pop("manifest", manifest("approved")), bundle["request"],
                                  grant=bundle.get("grant"), now=NOW,
                                  expected_source_sha=kwargs.pop("expected_source_sha", SOURCE))

    def test_build_admission_needs_no_attestation(self):
        record = self.prepare(FakeHost())
        self.assertTrue(record["admit_build"])
        self.assertEqual(record["coolify_uuid"], UUID)

    def test_held_lane_without_grant_cannot_build(self):
        bundle = {"request": request(), "grant": None}
        with self.assertRaises(Denied) as caught:
            self.prepare(FakeHost(), bundle=bundle, manifest=manifest("hold"))
        self.assertEqual(str(caught.exception), "release_lane_on_hold")

    def test_unreviewed_merge_cannot_build(self):
        bundle = {"request": request(approval=None), "grant": grant()}
        with self.assertRaises(Denied) as caught:
            self.prepare(FakeHost(), bundle=bundle)
        self.assertEqual(str(caught.exception), "independent_review_missing")

    def test_changed_head_after_review_cannot_build(self):
        approval = request()["approval"] | {"approved_sha": "e" * 40}
        bundle = {"request": request(approval=approval), "grant": grant()}
        with self.assertRaises(Denied) as caught:
            self.prepare(FakeHost(), bundle=bundle)
        self.assertEqual(str(caught.exception), "pr_head_changed_after_review")

    def test_unauthorized_uuid_cannot_build(self):
        bundle = {"request": request(coolify_uuid="0" * 24), "grant": grant()}
        with self.assertRaises(Denied) as caught:
            self.prepare(FakeHost(), bundle=bundle)
        self.assertEqual(str(caught.exception), "coolify_uuid_mismatch")

    def test_unreviewed_main_merge_cannot_build(self):
        bundle = {"request": request(merge_sha="f" * 40), "grant": grant()}
        with self.assertRaises(Denied) as caught:
            self.prepare(FakeHost(), bundle=bundle)
        self.assertEqual(str(caught.exception), "source_sha_not_merged_source")

    def test_expired_grant_cannot_build(self):
        bundle = {"request": request(), "grant": grant(expires_at=(NOW - timedelta(minutes=1)).isoformat())}
        with self.assertRaises(Denied) as caught:
            self.prepare(FakeHost(), bundle=bundle)
        self.assertEqual(str(caught.exception), "grant_expired")

    def test_prepare_builds_and_pushes_only_after_admission(self):
        host = FakeHost()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "mantic-mcp").mkdir()
            (Path(tmp) / "mantic-mcp" / "Dockerfile.http").write_text("FROM scratch\n", encoding="utf-8")
            with patch.object(delivery, "STATE_ROOT", Path(tmp)), \
                    patch.object(delivery, "verify_source", lambda *a: True):
                tag, digest = delivery.prepare(host, tmp, "mantic-mcp", SOURCE)
        self.assertIn("build", [call[0] for call in host.calls])
        self.assertIn(("docker", "push", tag), host.calls)
        self.assertEqual(digest, PREVIOUS)
        build_argv = [call for call in host.calls if call[0] == "build"][0]
        self.assertIn(f"org.opencontainers.image.revision={SOURCE}", build_argv)


class DeployStageTests(unittest.TestCase):
    """`--mode deploy`: run_promotion admits, the transport never rebuilds."""

    def bundle(self, **overrides):
        base = {"request": request(), "grant": grant(), "attestation": attestation()}
        base.update(overrides)
        return base

    def run_deploy(self, host, bundle, state_path=None, lock_path=None, promotion_state="approved"):
        with patch.object(delivery, "STATE_ROOT", Path(tempfile.mkdtemp())), \
                patch.object(delivery, "POLL_SECONDS", 0):
            return controller.run_promotion(manifest(promotion_state), ["mantic-mcp/src/server.ts"],
                                            lambda service: bundle, transport_for(host),
                                            now=NOW, state_path=state_path, lock_path=lock_path,
                                            source_sha=SOURCE)

    def assert_nothing_happened(self, report, host):
        self.assertFalse(report["promoted"])
        self.assertEqual(host.mutations(), [])
        self.assertIn("local/mantic-mcp:old", host.compose, "running compose must be untouched")

    def test_missing_attestation_deploys_nothing(self):
        host = FakeHost()
        report = self.run_deploy(host, self.bundle(attestation=None))
        self.assertEqual(report["decisions"][0]["reason"], "local_ci_attestation_missing")
        self.assert_nothing_happened(report, host)

    def test_stale_attestation_deploys_nothing(self):
        host = FakeHost()
        report = self.run_deploy(host, self.bundle(attestation=attestation(source_sha="f" * 40)))
        self.assertEqual(report["decisions"][0]["reason"], "attestation_stale_source_sha")
        self.assert_nothing_happened(report, host)

    def test_held_lane_deploys_nothing(self):
        host = FakeHost()
        report = self.run_deploy(host, self.bundle(grant=None), promotion_state="hold")
        self.assertEqual(report["decisions"][0]["reason"], "release_lane_on_hold")
        self.assert_nothing_happened(report, host)

    def test_expired_grant_deploys_nothing(self):
        host = FakeHost()
        report = self.run_deploy(host, self.bundle(grant=grant(expires_at=(NOW - timedelta(minutes=1)).isoformat())))
        self.assertEqual(report["decisions"][0]["reason"], "grant_expired")
        self.assert_nothing_happened(report, host)

    def test_unauthorized_uuid_deploys_nothing(self):
        host = FakeHost()
        report = self.run_deploy(host, self.bundle(request=request(coolify_uuid="0" * 24)))
        self.assertEqual(report["decisions"][0]["reason"], "coolify_uuid_mismatch")
        self.assert_nothing_happened(report, host)

    def test_unreviewed_main_merge_deploys_nothing(self):
        host = FakeHost()
        report = self.run_deploy(host, self.bundle(request=request(merge_sha="f" * 40)))
        self.assertEqual(report["decisions"][0]["reason"], "source_sha_not_merged_source")
        self.assert_nothing_happened(report, host)

    def test_admitted_deploy_patches_compose_and_reads_back(self):
        host = FakeHost(images={f"127.0.0.1:5000/harness-mantic-mcp:{SOURCE[:12]}": DIGEST})
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            with patch.object(delivery, "STATE_ROOT", Path(tmp)), patch.object(delivery, "POLL_SECONDS", 0):
                report = controller.run_promotion(
                    manifest("approved"), ["mantic-mcp/src/server.ts"], lambda service: self.bundle(),
                    transport_for(host), now=NOW, state_path=state, source_sha=SOURCE)
            self.assertTrue(state.exists())
        self.assertTrue(report["promoted"], report)
        self.assertIn(f"127.0.0.1:5000/harness-mantic-mcp@{DIGEST}", host.compose)
        self.assertNotIn(f"127.0.0.1:5000/harness-mantic-mcp:{SOURCE[:12]}", host.compose,
                         "a mutable tag must never be the deployed image reference")
        self.assertEqual([call[0] for call in host.calls].count("build"), 0,
                         "the deploy transport must never rebuild")

    def test_transport_deploys_attested_digest_not_retargetable_tag(self):
        host = FakeHost(images={
            f"127.0.0.1:5000/harness-mantic-mcp:{SOURCE[:12]}": PREVIOUS})
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)):
            deployment = transport_for(host).deploy("mantic-mcp", UUID, "service", DIGEST)
        self.assertEqual(deployment, "dep-1")
        self.assertIn(f"127.0.0.1:5000/harness-mantic-mcp@{DIGEST}", host.compose)
        self.assertNotIn(f"127.0.0.1:5000/harness-mantic-mcp:{SOURCE[:12]}", host.compose)
        self.assertEqual([call for call in host.calls if call[0] == "build"], [])

    def test_transport_rejects_invalid_digest_without_any_host_call(self):
        host = FakeHost()
        for invalid in ("sha256:abc", "not-a-digest", None, "sha256:" + "z" * 64):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(RuntimeError, "invalid immutable image digest"):
                    transport_for(host).deploy("mantic-mcp", UUID, "service", invalid)
        self.assertEqual(host.calls, [])
        self.assertEqual(host.compose, COMPOSE)

    def test_transport_refuses_an_image_with_a_foreign_revision(self):
        host = FakeHost(revision="f" * 40)
        with self.assertRaises(RuntimeError):
            transport_for(host).build("mantic-mcp", SOURCE)

    def test_transport_refuses_when_no_prepared_image_exists(self):
        host = FakeHost()
        host.images[f"127.0.0.1:5000/harness-mantic-mcp:{SOURCE[:12]}"] = None
        host.docker = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no such image"))
        with self.assertRaises(RuntimeError):
            transport_for(host).build("mantic-mcp", SOURCE)


class TransportTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(delivery, "POLL_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_compose_patch_replaces_exactly_one_image_line_and_is_backed_up(self):
        host = FakeHost()
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)):
            raw, backup = delivery.patch_compose(host, UUID, "mantic-mcp",
                                                 delivery.SERVICES["mantic-mcp"],
                                                 "127.0.0.1:5000/harness-mantic-mcp:" + SOURCE[:12])
            self.assertTrue(backup.exists())
            self.assertEqual(backup.read_text(encoding="utf-8"), raw)
        self.assertIn("127.0.0.1:5000/harness-mantic-mcp:" + SOURCE[:12], host.compose)

    def test_backup_filenames_are_unique_and_never_overwrite_a_previous_snapshot(self):
        host = FakeHost()
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)):
            _, first = delivery.patch_compose(host, UUID, "mantic-mcp",
                                              delivery.SERVICES["mantic-mcp"],
                                              "127.0.0.1:5000/harness-mantic-mcp:" + SOURCE[:12])
            first_content = first.read_text(encoding="utf-8")
            _, second = delivery.patch_compose(host, UUID, "mantic-mcp",
                                               delivery.SERVICES["mantic-mcp"],
                                               "127.0.0.1:5000/harness-mantic-mcp:" + ("f" * 12))
            self.assertNotEqual(first, second)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertEqual(first.read_text(encoding="utf-8"), first_content)
            self.assertEqual(first.stat().st_mode & 0o777, 0o600)
            self.assertEqual(second.stat().st_mode & 0o777, 0o600)

    def test_stale_disk_backup_cannot_be_used_as_rollback_authority(self):
        host = FakeHost()
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)):
            backup_dir = Path(tmp) / "backups"
            backup_dir.mkdir()
            (backup_dir / "mantic-mcp-stale.yml").write_text(
                "services:\n  mantic:\n    image: malicious-stale\n", encoding="utf-8")
            transport = transport_for(host)
            with self.assertRaisesRegex(RuntimeError, "no snapshot from this deployment attempt"):
                transport.rollback("mantic-mcp", UUID)
            self.assertEqual(host.calls, [], "stale backup must never authorize a PATCH/POST")

    def test_failed_deployment_restores_exact_snapshot_once(self):
        class FailingHost(FakeHost):
            def __init__(self):
                super().__init__()
                self.deploy_attempts = 0

            def coolify(self, method, path, body=None):
                if method == "POST" and path == "/deploy":
                    self.deploy_attempts += 1
                    if self.deploy_attempts == 1:
                        self.calls.append(("coolify", method, path))
                        raise RuntimeError("simulated deployment failure")
                return super().coolify(method, path, body)

        host = FailingHost()
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)):
            transport = transport_for(host)
            with self.assertRaisesRegex(RuntimeError, "simulated deployment failure"):
                transport.deploy("mantic-mcp", UUID, "service", DIGEST)
            self.assertNotEqual(host.compose, COMPOSE, "PATCH must have executed")
            transport.rollback("mantic-mcp", UUID)
            self.assertEqual(host.compose, COMPOSE)
            self.assertEqual(host.deploy_attempts, 2,
                             "one failing deploy and exactly one rollback deploy")
            with self.assertRaisesRegex(RuntimeError, "no snapshot from this deployment attempt"):
                transport.rollback("mantic-mcp", UUID)

    def test_rollback_coolify_accepted_is_not_success_without_live_health(self):
        host = FakeHost(service_status="running:unhealthy")
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)):
            transport = transport_for(host)
            delivery.patch_compose(
                host, UUID, "mantic-mcp", delivery.SERVICES["mantic-mcp"],
                f"127.0.0.1:5000/harness-mantic-mcp@{DIGEST}",
                on_backup=lambda backup: transport._rollback_snapshots.__setitem__(
                    ("mantic-mcp", UUID), backup))
            with patch.object(delivery, "HEALTH_DEADLINE", 0.5), \
                 patch.object(delivery, "POLL_SECONDS", 0), \
                 patch.object(delivery.time, "monotonic", side_effect=[0, 0, 1]):
                with self.assertRaisesRegex(RuntimeError, "rollback compose or live health not verified"):
                    transport.rollback("mantic-mcp", UUID)
        self.assertEqual(host.compose, COMPOSE, "Compose must be restored even on failed QA")
        self.assertEqual(host.calls.count(("coolify", "POST", "/deploy")), 1,
                         "an accepted rollback POST must not be repeated or declared healthy")

    def test_compose_patch_refuses_an_ambiguous_image_set(self):
        host = FakeHost(compose=COMPOSE + "  second:\n    image: local/mantic-mcp:also-old\n")
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)):
            with self.assertRaises(RuntimeError):
                delivery.patch_compose(host, UUID, "mantic-mcp", delivery.SERVICES["mantic-mcp"], "x")
        self.assertEqual(host.mutations(), [])

    def test_health_reports_the_running_digest_and_revision(self):
        host = FakeHost(compose=COMPOSE.replace("local/mantic-mcp:old",
                                               "127.0.0.1:5000/harness-mantic-mcp:" + SOURCE[:12]),
                        images={f"127.0.0.1:5000/harness-mantic-mcp:{SOURCE[:12]}": DIGEST})
        health = transport_for(host).health("mantic-mcp", UUID)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["digest"], DIGEST)
        self.assertEqual(health["source_sha"], SOURCE)

    def test_health_is_not_ok_when_the_service_is_unhealthy(self):
        host = FakeHost(service_status="running:unhealthy",
                        images={f"127.0.0.1:5000/harness-mantic-mcp:{SOURCE[:12]}": DIGEST},
                        compose=COMPOSE.replace("local/mantic-mcp:old",
                                                "127.0.0.1:5000/harness-mantic-mcp:" + SOURCE[:12]))
        self.assertNotEqual(transport_for(host).health("mantic-mcp", UUID)["status"], "ok")

    def test_current_reads_the_deployed_digest(self):
        host = FakeHost(images={"local/mantic-mcp:old": PREVIOUS})
        self.assertEqual(transport_for(host).current("mantic-mcp", UUID), PREVIOUS)


class SourceVerificationTests(unittest.TestCase):
    """The build must run on the reviewed tree, verified before docker is invoked."""

    def repo(self):
        import subprocess

        tmp = tempfile.mkdtemp()
        run = lambda *a: subprocess.run(list(a), cwd=tmp, capture_output=True, text=True, check=True)
        run("git", "init", "-q")
        run("git", "config", "user.email", "t@example.invalid")
        run("git", "config", "user.name", "test")
        (Path(tmp) / "mantic-mcp").mkdir()
        (Path(tmp) / "mantic-mcp" / "Dockerfile.http").write_text("FROM scratch\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "reviewed tree")
        sha = run("git", "rev-parse", "HEAD").stdout.strip()
        return tmp, sha, run

    def test_clean_tree_at_the_exact_sha_passes(self):
        repo, sha, _ = self.repo()
        self.assertTrue(delivery.verify_source(repo, sha))

    def test_foreign_head_is_refused(self):
        repo, sha, _ = self.repo()
        with self.assertRaises(Denied) as caught:
            delivery.verify_source(repo, "f" * 40)
        self.assertEqual(str(caught.exception), "source_not_at_approved_sha")

    def test_dirty_worktree_is_refused(self):
        repo, sha, _ = self.repo()
        (Path(repo) / "mantic-mcp" / "Dockerfile.http").write_text("FROM busybox\n", encoding="utf-8")
        with self.assertRaises(Denied) as caught:
            delivery.verify_source(repo, sha)
        self.assertEqual(str(caught.exception), "source_worktree_dirty")

    def test_untracked_build_context_file_is_refused(self):
        repo, sha, _ = self.repo()
        # An untracked file is not in the reviewed SHA but may enter COPY .
        (Path(repo) / "mantic-mcp" / "unreviewed.js").write_text(
            "process.exit(1)\n", encoding="utf-8")
        host = FakeHost()
        with self.assertRaises(Denied) as caught:
            delivery.verify_source(repo, sha)
        self.assertEqual(str(caught.exception), "source_worktree_dirty")
        self.assertEqual(host.calls, [], "untracked content must not reach Docker")

    def test_gitignored_build_context_file_is_refused(self):
        repo, sha, _ = self.repo()
        # .git/info/exclude is not committed; this file would be invisible
        # to ordinary git status but still present in a Docker COPY context.
        (Path(repo) / ".git" / "info" / "exclude").write_text(
            "mantic-mcp/ignored-build-input.js\n", encoding="utf-8")
        (Path(repo) / "mantic-mcp" / "ignored-build-input.js").write_text(
            "console.log('unreviewed');\n", encoding="utf-8")
        with self.assertRaises(Denied) as caught:
            delivery.verify_source(repo, sha)
        self.assertEqual(str(caught.exception), "source_worktree_dirty")

    def test_non_repository_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Denied) as caught:
                delivery.verify_source(tmp, SOURCE)
        self.assertEqual(str(caught.exception), "source_unreadable")

    def test_prepare_refuses_before_docker_when_the_tree_is_foreign(self):
        repo, _sha, _ = self.repo()
        host = FakeHost()
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)):
            with self.assertRaises(Denied) as caught:
                delivery.prepare(host, repo, "mantic-mcp", "f" * 40)
        self.assertEqual(str(caught.exception), "source_not_at_approved_sha")
        self.assertEqual(host.calls, [], "no docker call may happen before the source is verified")


class TransportMapTests(unittest.TestCase):
    """A manifest service the transport does not model must stop the run."""

    def test_transport_rejects_an_unmodelled_service(self):
        host = FakeHost()
        transport = transport_for(host)
        for call in (lambda: transport.build("mcp-edge", SOURCE),
                     lambda: transport.deploy("mcp-edge", UUID, "service", DIGEST),
                     lambda: transport.health("mcp-edge", UUID),
                     lambda: transport.rollback("mcp-edge", UUID)):
            with self.assertRaises(RuntimeError):
                call()
        self.assertEqual(host.calls, [])

    def test_deploy_run_refuses_a_manifest_service_outside_the_transport(self):
        host = FakeHost()
        man = manifest("approved")
        man["other_resources"].append({"id": "mcp-edge", "platform": "coolify",
                                       "coolify_kind": "service", "coolify_uuid": "z" * 24,
                                       "review_required": True, "exact_sha_required": True,
                                       "reviewer_role": "CHO", "promotion_state": "approved"})
        documents = {"request": request(), "grant": grant(), "attestation": attestation()}
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)), \
                patch.object(delivery, "Host", lambda *a, **k: host), \
                patch.object(delivery, "git_changed_paths",
                             lambda *a, **k: ["mantic-mcp/src/server.ts", "mcp-edge/src/x.ts"]), \
                patch.object(delivery, "load_gate_file",
                             side_effect=lambda path, label, require_root=False: (
                                 man if label == "manifest" else documents.get(label))):
            stderr = io.StringIO()
            with patch.object(sys, "stdout", io.StringIO()), patch.object(sys, "stderr", stderr):
                code = delivery.main(["--mode", "deploy", "--repo", ".", "--base-sha", "0" * 40,
                                      "--source-sha", SOURCE, "--artifact-dir", tmp])
        self.assertEqual(code, 1)
        self.assertIn("service_not_in_transport", stderr.getvalue())
        self.assertEqual(host.mutations(), [])


KEY = b"k" * 32


def signed_attestation(source_sha=SOURCE, results=None, **overrides):
    """A real HMAC attestation for the fixture service, as the attester writes it.

    The SHA is a parameter rather than an override because the signature covers
    every field: patching it after signing produces a (correctly) invalid artifact.
    """
    import harness_local_ci_attest as attester

    document = attester.build_attestation(
        "mantic-mcp", source_sha,
        results if results is not None else [{"command": "true", "exit": 0}],
        ["mantic-mcp/src/server.ts"], DIGEST, KEY, runner_uid=1000,
        policy_digest="sha256:" + "e" * 64)
    document.update(overrides)
    return document


def deliverables(documents):
    """Patch the artifact loader the delivery path uses: controller.load_artifacts."""
    return patch.object(controller, "load_gate_file",
                        side_effect=lambda path, label, require_root=True: documents.get(label))


class MainWiringTests(unittest.TestCase):
    """main() must route prepare through evaluate_build and deploy through run_promotion."""

    def run_main(self, mode, host, *, documents=None, changed=("mantic-mcp/src/server.ts",),
                 extra=(), source_sha=SOURCE, attestation_key=True):
        documents = documents if documents is not None else {
            "request": request(), "grant": grant(), "attestation": signed_attestation()}
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)), \
                patch.object(delivery, "Host", lambda *a, **k: host), \
                patch.object(delivery, "git_changed_paths", lambda *a, **k: list(changed)), \
                patch.object(delivery, "load_gate_file",
                             side_effect=lambda path, label, require_root=False: manifest()), \
                deliverables(documents), \
                patch.object(controller, "read_trusted_bytes",
                             lambda path, label, require_root=True: KEY):
            if mode == "prepare":
                (Path(tmp) / "mantic-mcp").mkdir()
                (Path(tmp) / "mantic-mcp" / "Dockerfile.http").write_text("FROM scratch\n", encoding="utf-8")
            argv = ["--mode", mode, "--repo", ".", "--base-sha", "0" * 40,
                    "--source-sha", source_sha, "--artifact-dir", tmp]
            if attestation_key:
                argv += ["--attestation-key", str(Path(tmp) / "key")]
            argv += list(extra)
            stdout = io.StringIO()
            with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", io.StringIO()):
                code = delivery.main(argv)
        return code, stdout.getvalue()

    def test_prepare_mode_denies_a_held_lane_and_builds_nothing(self):
        host = FakeHost()
        code, out = self.run_main("prepare", host,
                                  documents={"request": request(), "grant": None,
                                             "attestation": signed_attestation()})
        self.assertEqual(code, 1)
        self.assertEqual(host.mutations(), [])
        self.assertIn("release_lane_on_hold", out)

    def test_prepare_refuses_evidence_for_another_source_sha(self):
        # CTO finding 1: the CLI --source-sha decides what is built, so a request
        # and grant naming SHA A must deny a build of SHA B before docker runs.
        host = FakeHost()
        code, out = self.run_main("prepare", host, source_sha="9" * 40)
        self.assertEqual(code, 1)
        self.assertEqual(host.mutations(), [])
        self.assertIn("admission_source_sha_mismatch", out)

    def test_multi_service_batch_denial_prevents_any_partial_release(self):
        # One authorized service + an unregistered changed service must not
        # build/push/deploy even the authorized one before the full preflight.
        changes = ("mantic-mcp/src/server.ts", "playwright-mcp/src/unreviewed.js")
        for mode in ("prepare", "deploy"):
            host = FakeHost()
            code, out = self.run_main(mode, host, changed=changes,
                                      extra=["--now", NOW.isoformat()])
            self.assertEqual(code, 1, out)
            self.assertIn("unknown_service", out)
            self.assertEqual(host.calls, [], "admission failure must precede all host calls")

    def test_plan_mode_never_mutates(self):
        host = FakeHost()
        code, out = self.run_main("plan", host, extra=["--now", NOW.isoformat()])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(host.mutations(), [])
        self.assertEqual(payload["mode"], "plan")
        self.assertEqual(list(payload["services"]), ["mantic-mcp"])
        self.assertIsNone(payload["deployed"])

    def test_deploy_mode_denies_without_attestation_and_never_deploys(self):
        host = FakeHost()
        code, out = self.run_main("deploy", host,
                                  documents={"request": request(), "grant": grant(),
                                             "attestation": None},
                                  extra=["--now", NOW.isoformat()])
        payload = json.loads(out or "{}")
        self.assertEqual(code, 1)
        self.assertEqual(host.mutations(), [])
        self.assertEqual(payload["result"], "denied")
        self.assertIn("attestation", json.dumps(payload["denied"]))
        self.assertIsNone(payload.get("deployed"))

    def test_plan_with_missing_attestation_denies_without_host_mutation(self):
        host = FakeHost()
        code, out = self.run_main("plan", host,
                                  documents={"request": request(), "grant": grant(),
                                             "attestation": None},
                                  extra=["--now", NOW.isoformat()])
        self.assertEqual(code, 1)
        self.assertIn("attestation", out)
        self.assertEqual(host.mutations(), [])

    def test_deploy_denies_a_forged_signature_verified_artifact(self):
        # CTO finding 2: a raw JSON artifact claiming signature_verified=true used
        # to satisfy admission. It is now refused before any transport call.
        host = FakeHost()
        forged = dict(attestation())
        self.assertIs(forged["signature_verified"], True)
        code, out = self.run_main("deploy", host,
                                  documents={"request": request(), "grant": grant(),
                                             "attestation": forged})
        payload = json.loads(out or "{}")
        self.assertEqual(code, 1)
        self.assertEqual(host.mutations(), [])
        self.assertIn("attestation_signature_invalid", json.dumps(payload["denied"]))
        self.assertEqual(payload["result"], "denied")

    def test_deploy_denies_when_the_attestation_key_is_missing(self):
        host = FakeHost()
        code, out = self.run_main("deploy", host, attestation_key=False)
        payload = json.loads(out or "{}")
        self.assertEqual(code, 1)
        self.assertEqual(host.mutations(), [])
        self.assertIn("attestation_key_missing", json.dumps(payload["denied"]))

    def test_attestation_test_commands_are_never_executed(self):
        # "never invoke root-host arbitrary commands": an attestation carries the
        # commands the attester ran, and the delivery path only ever reads them.
        marker = "/bin/sh -c touch /root/pwned"
        host = FakeHost()
        documents = {"request": request(), "grant": grant(),
                     "attestation": signed_attestation(results=[{"command": marker, "exit": 0}])}
        code, out = self.run_main("deploy", host, documents=documents,
                                  extra=["--now", NOW.isoformat()])
        self.assertEqual(code, 1, out)
        self.assertNotIn("pwned", json.dumps([str(call) for call in host.calls]))


class AutoModeTests(unittest.TestCase):
    """`--auto` is the timer's invocation: exact operator input or a denial."""

    def repo(self, commits=2):
        import subprocess

        tmp = tempfile.mkdtemp()
        run = lambda *a: subprocess.run(list(a), cwd=tmp, capture_output=True, text=True, check=True)
        run("git", "init", "-q")
        run("git", "config", "user.email", "t@example.invalid")
        run("git", "config", "user.name", "test")
        (Path(tmp) / "mantic-mcp").mkdir()
        target = Path(tmp) / "mantic-mcp" / "Dockerfile.http"
        target.write_text("FROM scratch\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "base")
        first = run("git", "rev-parse", "HEAD").stdout.strip()
        for index in range(1, commits):
            target.write_text(f"FROM scratch\n# {index}\n", encoding="utf-8")
            run("git", "add", "-A")
            run("git", "commit", "-q", "-m", f"change {index}")
        return tmp, first, run("git", "rev-parse", "HEAD").stdout.strip()

    def documents_for(self, source_sha):
        """Evidence bound to the SHA the operator's range names."""
        return {"request": request(source_sha=source_sha, merge_sha=source_sha),
                "grant": grant(source_sha=source_sha),
                "attestation": signed_attestation(source_sha=source_sha)}

    def run_auto(self, repo, state_dir, mode="plan", host=None, documents=None,
                 source_sha=SOURCE, environ=None):
        host = host or FakeHost()
        documents = documents if documents is not None else self.documents_for(source_sha)
        environment = {k: v for k, v in (environ or {}).items() if v is not None}
        with patch.object(delivery, "STATE_ROOT", Path(state_dir)), \
                patch.object(delivery, "POLL_SECONDS", 0), \
                patch.object(delivery, "Host", lambda *a, **k: host), \
                patch.object(delivery, "load_gate_file",
                             side_effect=lambda path, label, require_root=False: manifest()), \
                deliverables(documents), \
                patch.object(controller, "read_trusted_bytes",
                             lambda path, label, require_root=True: KEY), \
                patch.dict(os.environ, environment, clear=False), \
                patch.dict(os.environ, {k: v for k, v in {"HARNESS_BASE_SHA": "",
                                                          "HARNESS_SOURCE_SHA": ""}.items()
                                        if k not in environment}):
            argv = ["--mode", mode, "--auto", "--repo", repo, "--state-dir", state_dir,
                    "--artifact-dir", state_dir, "--attestation-key", str(Path(state_dir) / "key"),
                    "--now", NOW.isoformat()]
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
                code = delivery.main(argv)
        return code, stdout.getvalue() + stderr.getvalue(), host

    def test_the_installed_timer_invocation_is_accepted(self):
        # The legacy unit ran `--auto` with nothing else; the old adapter exited 2
        # on that. The reviewed invocation must parse.
        delivery.build_parser().parse_args(["--mode", "deploy", "--auto"])
        delivery.build_parser().parse_args(["--auto"])

    def test_auto_uses_the_exact_range_from_the_unit_environment(self):
        repo, base, head = self.repo()
        code, out, host = self.run_auto(repo, tempfile.mkdtemp(), source_sha=head,
                                        environ={"HARNESS_BASE_SHA": base,
                                                 "HARNESS_SOURCE_SHA": head})
        payload = json.loads(out)
        self.assertEqual(code, 0, out)
        self.assertEqual(payload["source_sha"], head)
        self.assertEqual(list(payload["services"]), ["mantic-mcp"])
        self.assertEqual(host.mutations(), [])

    def test_auto_without_an_operator_range_fails_closed(self):
        repo, base, head = self.repo()
        code, out, host = self.run_auto(repo, tempfile.mkdtemp(), environ={})
        self.assertEqual(code, 1)
        self.assertIn("auto_source_range_missing", out)
        self.assertEqual(host.mutations(), [])

    def test_auto_rejects_a_malformed_range(self):
        repo, base, head = self.repo()
        code, out, host = self.run_auto(repo, tempfile.mkdtemp(),
                                        environ={"HARNESS_BASE_SHA": "not-a-sha",
                                                 "HARNESS_SOURCE_SHA": head})
        self.assertEqual(code, 1)
        self.assertIn("invalid_base_sha", out)
        self.assertEqual(host.mutations(), [])

    def test_auto_invents_no_state_and_keeps_no_baseline(self):
        # Owner constraint: no additional state system. Nothing is written that a
        # later run could mistake for a delivery baseline.
        repo, base, head = self.repo()
        state_dir = tempfile.mkdtemp()
        code, out, host = self.run_auto(repo, state_dir, mode="prepare", source_sha=head,
                                        environ={"HARNESS_BASE_SHA": base,
                                                 "HARNESS_SOURCE_SHA": head})
        self.assertEqual(code, 0, out)
        state_files = sorted(p.name for p in Path(state_dir).iterdir() if p.suffix == ".json")
        self.assertEqual(state_files, [],
                         "the cycle must not create a baseline or any other JSON state")

    def test_auto_reports_no_change_when_the_range_is_empty(self):
        repo, base, head = self.repo()
        code, out, host = self.run_auto(repo, tempfile.mkdtemp(), source_sha=head,
                                        environ={"HARNESS_BASE_SHA": head,
                                                 "HARNESS_SOURCE_SHA": head})
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(payload["result"], "no_change")
        self.assertEqual(host.mutations(), [])

    def test_auto_denies_a_held_lane_without_touching_the_host(self):
        repo, base, head = self.repo()
        documents = self.documents_for(head)
        documents["grant"] = None
        code, out, host = self.run_auto(repo, tempfile.mkdtemp(), mode="deploy", documents=documents,
                                        source_sha=head,
                                        environ={"HARNESS_BASE_SHA": base,
                                                 "HARNESS_SOURCE_SHA": head})
        self.assertEqual(code, 1, out)
        self.assertEqual(host.mutations(), [])
        self.assertIn("release_lane_on_hold", out)

    def test_explicit_mode_still_requires_both_shas(self):
        args = delivery.build_parser().parse_args(["--mode", "plan"])
        with self.assertRaises(Denied) as caught:
            delivery.resolve_source_range(args, environ={})
        self.assertEqual(str(caught.exception), "sha_arguments_required")


if __name__ == "__main__":
    unittest.main()
