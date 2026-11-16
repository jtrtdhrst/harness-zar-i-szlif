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
    return base


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
                                  grant=bundle.get("grant"), now=NOW)

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
            with patch.object(delivery, "STATE_ROOT", Path(tmp)):
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
                                            now=NOW, state_path=state_path, lock_path=lock_path)

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
                    transport_for(host), now=NOW, state_path=state)
            self.assertTrue(state.exists())
        self.assertTrue(report["promoted"], report)
        self.assertIn(f"127.0.0.1:5000/harness-mantic-mcp:{SOURCE[:12]}", host.compose)
        self.assertEqual([call[0] for call in host.calls].count("build"), 0,
                         "the deploy transport must never rebuild")

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


class MainWiringTests(unittest.TestCase):
    """main() must route prepare through evaluate_build and deploy through run_promotion."""

    def run_main(self, mode, host, *, artifacts=True, changed=("mantic-mcp/src/server.ts",)):
        documents = {"request": request(), "grant": grant(), "attestation": attestation()}
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)), \
                patch.object(delivery, "Host", lambda *a, **k: host), \
                patch.object(delivery, "git_changed_paths", lambda *a, **k: list(changed)), \
                patch.object(delivery, "load_gate_file",
                             side_effect=lambda path, label, require_root=False: (
                                 manifest() if label == "manifest" else documents[label])):
            if mode == "prepare":
                (Path(tmp) / "mantic-mcp").mkdir()
                (Path(tmp) / "mantic-mcp" / "Dockerfile.http").write_text("FROM scratch\n", encoding="utf-8")
            stdout = io.StringIO()
            with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", io.StringIO()):
                code = delivery.main(["--mode", mode, "--repo", ".",
                                      "--base-sha", "0" * 40, "--source-sha", SOURCE,
                                      "--artifact-dir" if artifacts else "--repo",
                                      tmp if artifacts else "."])
        return code, stdout.getvalue()

    def test_prepare_mode_denies_a_held_lane_and_builds_nothing(self):
        host = FakeHost()
        documents = {"request": request(), "grant": None, "attestation": attestation()}
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)), \
                patch.object(delivery, "Host", lambda *a, **k: host), \
                patch.object(delivery, "git_changed_paths", lambda *a, **k: ["mantic-mcp/src/server.ts"]), \
                patch.object(delivery, "load_gate_file",
                             side_effect=lambda path, label, require_root=False: (
                                 manifest() if label == "manifest" else documents.get(label))):
            (Path(tmp) / "mantic-mcp").mkdir()
            (Path(tmp) / "mantic-mcp" / "Dockerfile.http").write_text("FROM scratch\n", encoding="utf-8")
            stdout = io.StringIO()
            with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", io.StringIO()):
                code = delivery.main(["--mode", "prepare", "--repo", ".", "--base-sha", "0" * 40,
                                      "--source-sha", SOURCE, "--artifact-dir", tmp])
        self.assertEqual(code, 0)
        self.assertEqual(host.mutations(), [])
        self.assertIn("release_lane_on_hold", stdout.getvalue())

    def test_plan_mode_never_mutates(self):
        host = FakeHost()
        code, out = self.run_main("plan", host)
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(host.mutations(), [])
        self.assertEqual(payload["mode"], "plan")
        self.assertEqual(list(payload["services"]), ["mantic-mcp"])
        self.assertIsNone(payload["deployed"])

    def test_deploy_mode_denies_without_attestation_and_never_deploys(self):
        host = FakeHost()
        documents = {"request": request(), "grant": grant(), "attestation": None}
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery, "STATE_ROOT", Path(tmp)), \
                patch.object(delivery, "Host", lambda *a, **k: host), \
                patch.object(delivery, "git_changed_paths", lambda *a, **k: ["mantic-mcp/src/server.ts"]), \
                patch.object(delivery, "load_gate_file",
                             side_effect=lambda path, label, require_root=False: (
                                 manifest() if label == "manifest" else documents.get(label))):
            stdout = io.StringIO()
            with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", io.StringIO()):
                code = delivery.main(["--mode", "deploy", "--repo", ".", "--base-sha", "0" * 40,
                                      "--source-sha", SOURCE, "--artifact-dir", tmp,
                                      "--now", NOW.isoformat()])
        payload = json.loads(stdout.getvalue() or "{}")
        self.assertEqual(code, 0)
        self.assertEqual(host.mutations(), [])
        deployed = payload.get("deployed") or {}
        self.assertFalse(deployed.get("promoted"))
        self.assertEqual(deployed["decisions"][0]["reason"], "local_ci_attestation_missing")


if __name__ == "__main__":
    unittest.main()
