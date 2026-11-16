"""Fail-closed tests for the hold-aware Harness delivery controller (ZARI-240).

The controller is the reviewed promotion path the root-owned host unit must
call. Every negative case below asserts the same invariant: a held, unreviewed,
stale or unattributable merge produces an admission denial, **zero transport
calls**, and an unchanged running image.
"""
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import harness_delivery_controller as controller
import harness_release_admission as gate

NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
SOURCE = "a" * 40
HEAD = "b" * 40
DIGEST = "sha256:" + "c" * 64
UUID = "bioufw4uxwuhmr51ueyahf0u"
KEY = b"k" * 32


def manifest(promotion_state=None, service="mantic-mcp", uuid=UUID):
    entry = {
        "id": service,
        "platform": "coolify",
        "coolify_kind": "service",
        "coolify_uuid": uuid,
        "review_required": True,
        "exact_sha_required": True,
        "reviewer_role": "CHO",
    }
    if promotion_state is not None:
        entry["promotion_state"] = promotion_state
    return {"schema_version": 1, "owner": "CHO", "lanes": [], "other_resources": [entry],
            "cloudflare_workers": [{"id": "placeholder"}]}


def request(**overrides):
    base = {
        "service": "mantic-mcp",
        "coolify_uuid": UUID,
        "coolify_kind": "service",
        "pr": 112,
        "base_ref": "main",
        "head_sha": HEAD,
        "source_sha": SOURCE,
        "merge_sha": SOURCE,
        "image_digest": DIGEST,
        "approval": {"reviewer_role": "CHO", "reviewer_agent_id": "reviewer-agent",
                     "producer_agent_id": "producer-agent", "approved_sha": HEAD},
    }
    base.update(overrides)
    return base


def attestation(**overrides):
    base = {
        "schema_version": 1,
        "signature_verified": True,
        "attestor_uid": 0,
        "runner_uid": 1000,
        "policy_digest": "sha256:" + "e" * 64,
        "service": "mantic-mcp",
        "source_sha": SOURCE,
        "image_digest": DIGEST,
        "tests": [{"command": "/usr/bin/python3 -m unittest -q", "exit": 0}],
        "changed_paths": ["mantic-mcp/src/server.ts"],
        "artifact_manifest_digest": "sha256:" + "d" * 64,
    }
    base.update(overrides)
    return base


def grant(**overrides):
    base = {
        "schema_version": 1,
        "revoked": False,
        "coolify_uuid": UUID,
        "service": "mantic-mcp",
        "source_sha": SOURCE,
        "grant_id": "grant-20261116-mantic",
        "granted_by": "owner",
        "expires_at": (NOW + timedelta(hours=4)).isoformat(),
    }
    base.update(overrides)
    return base


def bundle(**overrides):
    data = {"request": request(), "grant": grant(), "attestation": attestation()}
    data.update(overrides)
    return data


class FakeTransport:
    """Records every transport call and models the running image per service."""

    def __init__(self, running=None, build_digest=None, health=None,
                 deploy_error=None, health_result=None):
        self.calls = []
        self.running = dict(running or {})
        self.build_digest = build_digest or DIGEST
        self.health_result = health_result
        self.deploy_error = deploy_error
        self.rollback_target = dict(running or {})

    def current(self, service, uuid):
        self.calls.append("current")
        return self.running.get(service)

    def build(self, service, source_sha):
        self.calls.append("build")
        return self.build_digest

    def deploy(self, service, uuid, kind, digest):
        self.calls.append("deploy")
        if self.deploy_error:
            raise self.deploy_error
        self.running[service] = digest
        return "deploy-1"

    def health(self, service, uuid):
        self.calls.append("health")
        if self.health_result is not None:
            return self.health_result
        return {"status": "ok", "digest": self.running.get(service), "source_sha": SOURCE}

    def rollback(self, service, uuid):
        self.calls.append("rollback")
        if service in self.rollback_target:
            self.running[service] = self.rollback_target[service]
        else:
            self.running.pop(service, None)
        return "rollback-1"


PREVIOUS = "sha256:" + "9" * 64


class ControllerRefusalTests(unittest.TestCase):
    def run_controller(self, transport, artifacts=None, paths=("mantic-mcp/src/server.ts",),
                       man=None, state_path=None, lock_path=None):
        return controller.run_promotion(man or manifest(), list(paths),
                                        artifacts or (lambda service: bundle()), transport,
                                        now=NOW, state_path=state_path, lock_path=lock_path)

    def assert_no_mutation(self, report, transport):
        self.assertFalse(report["promoted"])
        self.assertFalse(report["mutated"])
        self.assertEqual(transport.calls, [], "no transport may be called on denial")
        self.assertEqual(transport.running, {"mantic-mcp": PREVIOUS})

    def test_held_lane_never_reaches_build_or_deploy(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        report = self.run_controller(transport, artifacts=lambda service: bundle(grant=None))
        self.assertEqual(report["decisions"][0]["reason"], "release_lane_on_hold")
        self.assertEqual(report["result"], "held")
        self.assert_no_mutation(report, transport)

    def test_unreviewed_merge_never_reaches_build_or_deploy(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        report = self.run_controller(transport, artifacts=lambda service: bundle(request=request(approval=None)))
        self.assertEqual(report["decisions"][0]["reason"], "independent_review_missing")
        self.assert_no_mutation(report, transport)

    def test_self_review_never_reaches_build_or_deploy(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        approval = request()["approval"] | {"reviewer_agent_id": "producer-agent"}
        report = self.run_controller(transport, artifacts=lambda service: bundle(request=request(approval=approval)))
        self.assertEqual(report["decisions"][0]["reason"], "self_review_forbidden")
        self.assert_no_mutation(report, transport)

    def test_changed_pr_head_after_review_never_reaches_build_or_deploy(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        approval = request()["approval"] | {"approved_sha": "e" * 40}
        report = self.run_controller(transport, artifacts=lambda service: bundle(request=request(approval=approval)))
        self.assertEqual(report["decisions"][0]["reason"], "pr_head_changed_after_review")
        self.assert_no_mutation(report, transport)

    def test_stale_attestation_never_reaches_build_or_deploy(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        report = self.run_controller(transport,
                                     artifacts=lambda service: bundle(attestation=attestation(source_sha="f" * 40)))
        self.assertEqual(report["decisions"][0]["reason"], "attestation_stale_source_sha")
        self.assert_no_mutation(report, transport)

    def test_revoked_grant_never_reaches_build_or_deploy(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        report = self.run_controller(transport, artifacts=lambda service: bundle(grant=grant(revoked=True)))
        self.assertEqual(report["decisions"][0]["reason"], "grant_revoked")
        self.assert_no_mutation(report, transport)

    def test_service_directory_outside_the_manifest_promotes_nothing(self):
        # A new or unknown service root is not promotable until the manifest
        # (reviewed) declares it, so its change can never reach a transport.
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        report = self.run_controller(transport, paths=("unlisted-mcp/src/server.ts",))
        self.assertEqual(report["result"], "no_service_change")
        self.assertEqual(report["unclassified_paths"], ["unlisted-mcp/src/server.ts"])
        self.assert_no_mutation(report, transport)

    def test_documentation_change_alongside_a_service_change_still_gates_the_service(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        report = self.run_controller(
            transport, paths=("docs/SOURCE-ONLY-AND-LOCAL-BUILDS.md", "mantic-mcp/src/server.ts"),
            artifacts=lambda service: bundle(grant=None))
        self.assertEqual(report["unclassified_paths"], ["docs/SOURCE-ONLY-AND-LOCAL-BUILDS.md"])
        self.assertEqual(report["decisions"][0]["reason"], "release_lane_on_hold")
        self.assert_no_mutation(report, transport)

    def test_malformed_changed_path_is_refused_before_any_decision(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        report = self.run_controller(transport, paths=("/etc/passwd",))
        self.assertEqual(report["reason"], "changed_paths_invalid")
        self.assert_no_mutation(report, transport)

    def test_empty_changed_paths_are_refused(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        report = controller.run_promotion(manifest(), [], lambda service: bundle(), transport, now=NOW)
        self.assertEqual(report["reason"], "changed_paths_invalid")
        self.assertEqual(transport.calls, [])

    def test_manifest_duplicate_service_is_ambiguous(self):
        man = manifest()
        man["lanes"].append(dict(man["other_resources"][0]))
        with self.assertRaises(gate.Denied):
            controller.manifest_services(man)

    def test_documentation_only_change_promotes_nothing(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        report = self.run_controller(transport, paths=("docs/SOURCE-ONLY-AND-LOCAL-BUILDS.md",))
        self.assertEqual(report["result"], "no_service_change")
        self.assertEqual(report["unclassified_paths"], ["docs/SOURCE-ONLY-AND-LOCAL-BUILDS.md"])
        self.assertEqual(transport.calls, [])

    def test_lock_contention_denies_without_transport_calls(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "controller.lock"
            with open(lock, "a+", encoding="utf-8") as held:
                import fcntl

                fcntl.flock(held.fileno(), fcntl.LOCK_EX)
                report = self.run_controller(transport, lock_path=lock)
            self.assertEqual(report["reason"], "controller_locked")
            self.assertEqual(transport.calls, [])

    def test_incomplete_transport_never_mutates(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        transport.rollback = None
        report = self.run_controller(transport)
        self.assertEqual(report["reason"], "transport_incomplete")
        self.assertEqual(transport.calls, [])


class ControllerPromotionTests(unittest.TestCase):
    def authorized(self, transport, **kwargs):
        return controller.run_promotion(
            manifest(promotion_state="approved"), ["mantic-mcp/src/server.ts"],
            lambda service: bundle(), transport, now=NOW, **kwargs)

    def test_authorized_change_is_built_deployed_and_read_back(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS})
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            report = self.authorized(transport, state_path=state)
            written = json.loads(state.read_text(encoding="utf-8"))
        self.assertTrue(report["promoted"])
        self.assertEqual(transport.calls, ["current", "build", "deploy", "health"])
        self.assertEqual(transport.running["mantic-mcp"], DIGEST)
        self.assertEqual(written["mantic-mcp"]["image_digest"], DIGEST)
        self.assertEqual(written["mantic-mcp"]["source_sha"], SOURCE)
        self.assertTrue(report["audit_id"].startswith("sha256:"))

    def test_build_digest_mismatch_is_never_deployed(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS},
                                  build_digest="sha256:" + "8" * 64)
        report = self.authorized(transport)
        self.assertEqual(report["decisions"][0]["reason"], "build_digest_mismatch")
        self.assertEqual(transport.calls, ["current", "build"])
        self.assertEqual(transport.running["mantic-mcp"], PREVIOUS)
        self.assertFalse(report["mutated"])

    def test_failed_health_rolls_back_exactly_once(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS},
                                  health_result={"status": "degraded", "digest": DIGEST})
        report = self.authorized(transport)
        self.assertEqual(report["decisions"][0]["decision"], "rolled_back")
        self.assertEqual(transport.calls.count("rollback"), 1)
        self.assertEqual(transport.running["mantic-mcp"], PREVIOUS)
        self.assertFalse(report["promoted"])

    def test_health_reporting_the_wrong_source_sha_rolls_back(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS},
                                  health_result={"status": "ok", "digest": DIGEST, "source_sha": "f" * 40})
        report = self.authorized(transport)
        self.assertEqual(report["decisions"][0]["reason"], "post_deploy_source_sha_mismatch")
        self.assertEqual(transport.calls.count("rollback"), 1)

    def test_deploy_exception_rolls_back(self):
        transport = FakeTransport(running={"mantic-mcp": PREVIOUS}, deploy_error=RuntimeError("boom"))
        report = self.authorized(transport)
        self.assertEqual(report["decisions"][0]["decision"], "rolled_back")
        self.assertEqual(transport.calls.count("rollback"), 1)
        self.assertEqual(transport.running["mantic-mcp"], PREVIOUS)

    def test_rerun_of_delivered_sha_does_not_rebuild(self):
        transport = FakeTransport(running={"mantic-mcp": DIGEST})
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text(json.dumps({"mantic-mcp": {"source_sha": SOURCE, "image_digest": DIGEST}}),
                             encoding="utf-8")
            report = self.authorized(transport, state_path=state)
        self.assertEqual(report["decisions"][0]["decision"], "already_delivered")
        self.assertEqual(transport.calls, ["current"])
        self.assertFalse(report["mutated"])

    def test_plan_mode_reports_admissible_without_transport(self):
        report = controller.run_promotion(manifest(promotion_state="approved"),
                                          ["mantic-mcp/src/server.ts"],
                                          lambda service: bundle(), None, now=NOW)
        self.assertEqual(report["decisions"][0]["decision"], "admissible_no_transport")
        self.assertFalse(report["promoted"])


class GateFileLoadingTests(unittest.TestCase):
    """Descriptor-validated reads: symlink, ownership, size and swap controls."""

    def write(self, tmp, name, payload, mode=0o600):
        path = Path(tmp) / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        os.chmod(path, mode)
        return path

    def test_reads_a_trusted_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "request.json", {"ok": True})
            self.assertEqual(gate.load_gate_file(path, "request", require_root=False), {"ok": True})

    def test_symlinked_artifact_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = self.write(tmp, "real.json", {"ok": True})
            link = Path(tmp) / "link.json"
            link.symlink_to(real)
            with self.assertRaisesRegex(gate.Denied, "request_symlink_refused"):
                gate.load_gate_file(link, "request", require_root=False)

    def test_world_writable_artifact_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "request.json", {"ok": True}, mode=0o666)
            with self.assertRaisesRegex(gate.Denied, "request_world_writable"):
                gate.load_gate_file(path, "request", require_root=False)

    def test_non_root_owned_artifact_is_refused_when_root_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "request.json", {"ok": True})
            if os.geteuid() == 0:
                self.assertEqual(gate.load_gate_file(path, "request", require_root=True), {"ok": True})
            else:
                with self.assertRaisesRegex(gate.Denied, "request_not_root_owned"):
                    gate.load_gate_file(path, "request", require_root=True)

    def test_empty_and_oversized_artifacts_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.json"
            empty.write_bytes(b"")
            os.chmod(empty, 0o600)
            with self.assertRaisesRegex(gate.Denied, "request_invalid_size"):
                gate.load_gate_file(empty, "request", require_root=False)
            big = Path(tmp) / "big.json"
            big.write_bytes(b"{" + b" " * 262145 + b"}")
            os.chmod(big, 0o600)
            with self.assertRaisesRegex(gate.Denied, "request_invalid_size"):
                gate.load_gate_file(big, "request", require_root=False)

    def test_invalid_json_and_wrong_shape_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("not json", encoding="utf-8")
            os.chmod(bad, 0o600)
            with self.assertRaisesRegex(gate.Denied, "request_invalid_json"):
                gate.load_gate_file(bad, "request", require_root=False)
            listing = Path(tmp) / "list.json"
            listing.write_text("[]", encoding="utf-8")
            os.chmod(listing, 0o600)
            with self.assertRaisesRegex(gate.Denied, "request_invalid_shape"):
                gate.load_gate_file(listing, "request", require_root=False)

    def test_path_swapped_for_a_symlink_never_yields_attacker_bytes(self):
        """Regression for the CTO finding on PR #112 at e52f74f.

        The loader used to lstat() and then reopen by path, so a path swapped to
        a symlink between the two calls was trusted. The descriptor-validated
        read can only ever return the bytes of the file it validated.
        """
        with tempfile.TemporaryDirectory() as tmp:
            trusted = self.write(tmp, "trusted.json", {"marker": "trusted"})
            evil = self.write(tmp, "evil.json", {"marker": "attacker"})
            target = Path(tmp) / "request.json"
            target.write_text(json.dumps({"marker": "trusted"}), encoding="utf-8")
            os.chmod(target, 0o600)
            stop = threading.Event()

            def swapper():
                counter = 0
                while not stop.is_set():
                    link = Path(tmp) / ("swap.%d" % counter)
                    good = Path(tmp) / ("swap.%d.good" % counter)
                    counter += 1
                    try:
                        link.symlink_to(evil)
                        os.replace(link, target)
                        good.write_text(trusted.read_text(encoding="utf-8"), encoding="utf-8")
                        os.chmod(good, 0o600)
                        os.replace(good, target)
                    except OSError:
                        continue

            thread = threading.Thread(target=swapper, daemon=True)
            thread.start()
            attacker_reads = 0
            for _ in range(2000):
                try:
                    data = gate.load_gate_file(target, "request", require_root=False)
                except gate.Denied:
                    continue
                if data.get("marker") == "attacker":
                    attacker_reads += 1
            stop.set()
            thread.join(timeout=5)
            self.assertEqual(attacker_reads, 0, "a swapped path must never be trusted")


class AttestationKeyTests(unittest.TestCase):
    """The key that verifies an attestation must itself be a trusted file."""

    def prepared_documents(self):
        attestation_doc = attestation()
        attestation_doc["signature"] = "0" * 64
        return {"manifest": manifest(), "request": request(), "grant": grant(),
                "attestation": attestation_doc}

    def run_main(self, key_path):
        documents = self.prepared_documents()
        stderr = io.StringIO()
        with patch.object(gate, "load_gate_file",
                          side_effect=lambda path, name, require_root=True: dict(documents[name])), \
                patch.object(sys, "stdout", io.StringIO()), \
                patch.object(sys, "stderr", stderr):
            code = gate.main(["--manifest", "m", "--request", "r", "--grant", "g",
                              "--attestation", "a", "--attestation-key", str(key_path)])
        return code, stderr.getvalue()

    def test_symlinked_attestation_key_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "attacker.key"
            key.write_bytes(KEY)
            os.chmod(key, 0o600)
            link = Path(tmp) / "key.link"
            link.symlink_to(key)
            code, stderr = self.run_main(link)
            self.assertEqual(code, 1)
            self.assertIn("attestation_key_symlink_refused", stderr)

    def test_untrusted_attestation_key_owner_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "attacker.key"
            key.write_bytes(KEY)
            os.chmod(key, 0o600)
            code, stderr = self.run_main(key)
            if os.geteuid() == 0:
                self.assertEqual(code, 1)          # signature is bogus, but the key was read
                self.assertIn("attestation_signature_invalid", stderr)
            else:
                self.assertEqual(code, 1)
                self.assertIn("attestation_key_not_root_owned", stderr)


if __name__ == "__main__":
    unittest.main()
