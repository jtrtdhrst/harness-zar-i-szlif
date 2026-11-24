"""Fail-closed tests for the Harness MCP release admission gate (ZARI-240).

Every negative case below is the control for a way an unreviewed or held merge
could otherwise reach Coolify. A denial is the admission gate's only output in
that case, so no image is promoted and the previously running image stays
untouched; the controller must never see an admission record to act on.
"""
import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import harness_release_admission as gate

NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
SOURCE = "a" * 40
HEAD = "b" * 40
DIGEST = "sha256:" + "c" * 64
UUID = "bioufw4uxwuhmr51ueyahf0u"


def manifest(promotion_state=None, reviewer_role="CHO"):
    entry = {
        "id": "mantic-mcp",
        "platform": "coolify",
        "coolify_kind": "service",
        "coolify_uuid": UUID,
        "review_required": True,
        "exact_sha_required": True,
        "reviewer_role": reviewer_role,
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
        "pr": 108,
        "base_ref": "main",
        "head_sha": HEAD,
        "source_sha": SOURCE,
        "merge_sha": SOURCE,
        "image_digest": DIGEST,
        "approval": {
            "reviewer_role": "CHO",
            "reviewer_agent_id": "reviewer-agent",
            "producer_agent_id": "producer-agent",
            "approved_sha": HEAD,
        },
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
        "tests": [{"command": "python -m pytest -q", "exit": 0}],
        "changed_paths": ["mcp/mantic-mcp/src/server.ts"],
        "artifact_manifest_digest": "sha256:" + "d" * 64,
    }
    base.update(overrides)
    # Admission accepts only an attestation whose HMAC was verified in-process,
    # which load_artifacts/verified_attestation marks with this type. A plain
    # dict - whatever it claims - is not evidence.
    return gate.VerifiedAttestation(base)


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


class AdmissionTests(unittest.TestCase):
    def deny(self, reason, **kwargs):
        kwargs.setdefault("grant", grant())
        kwargs.setdefault("attestation", attestation())
        kwargs.setdefault("expected_source_sha", SOURCE)
        with self.assertRaises(gate.Denied) as caught:
            gate.evaluate(kwargs.pop("manifest", manifest()), kwargs.pop("request", request()),
                          now=kwargs.pop("now", NOW), **kwargs)
        self.assertEqual(str(caught.exception), reason)

    def test_admits_fully_evidenced_promotion(self):
        record = gate.evaluate(manifest(), request(), grant=grant(), attestation=attestation(), now=NOW, expected_source_sha=SOURCE)
        self.assertTrue(record["admit"])
        self.assertEqual(record["source_sha"], SOURCE)
        self.assertEqual(record["image_digest"], DIGEST)
        self.assertEqual(record["grant_id"], "grant-20261116-mantic")

    def test_denies_unknown_service(self):
        self.deny("unknown_service", request=request(service="not-a-service"))

    def test_denies_non_allowlisted_coolify_uuid(self):
        self.deny("coolify_uuid_mismatch", request=request(coolify_uuid="0" * 24))

    def test_denies_held_lane_without_grant(self):
        # The regression for the reported defect: ops/release-lanes.json holds
        # every MCP resource, and the controller previously ignored it.
        self.deny("release_lane_on_hold", grant=None)

    def test_denies_missing_grant_even_when_manifest_approved(self):
        self.deny("per_uuid_grant_missing", manifest=manifest(promotion_state="approved"), grant=None)

    def test_lane_without_promotion_state_is_held(self):
        self.deny("release_lane_on_hold", manifest=manifest(promotion_state=None), grant=None)

    def test_denies_revoked_grant(self):
        self.deny("grant_revoked", grant=grant(revoked=True))

    def test_denies_expired_grant(self):
        self.deny("grant_expired", grant=grant(expires_at=(NOW - timedelta(minutes=1)).isoformat()))

    def test_denies_grant_for_another_uuid(self):
        self.deny("grant_uuid_mismatch", grant=grant(coolify_uuid="1" * 24))

    def test_denies_self_review(self):
        approval = request()["approval"] | {"reviewer_agent_id": "producer-agent"}
        self.deny("self_review_forbidden", request=request(approval=approval))

    def test_denies_wrong_reviewer_role(self):
        approval = request()["approval"] | {"reviewer_role": "CTO"}
        self.deny("wrong_reviewer_role", request=request(approval=approval))

    def test_denies_changed_pr_head_after_review(self):
        approval = request()["approval"] | {"approved_sha": "e" * 40}
        self.deny("pr_head_changed_after_review", request=request(approval=approval))

    def test_denies_unreviewed_merge_without_approval(self):
        self.deny("independent_review_missing", request=request(approval=None))

    def test_denies_missing_attestation(self):
        self.deny("local_ci_attestation_missing", attestation=None)

    def test_denies_unverified_attestation_signature(self):
        self.deny("attestation_signature_unverified", attestation=attestation(signature_verified=False))

    def test_denies_attestation_not_produced_as_root(self):
        self.deny("attestation_not_root_owned", attestation=attestation(attestor_uid=1000))

    def test_denies_attestation_whose_tests_ran_as_root(self):
        # Owner security finding on PR #112: a root-executed test run is never
        # releasable evidence, whatever else the attestation claims.
        for runner in (0, None, -1, True):
            self.deny("attestation_test_runner_not_privilege_dropped",
                      attestation=attestation(runner_uid=runner))

    def test_denies_attestation_without_policy_digest(self):
        for digest in (None, "", "sha256:short", 42):
            self.deny("attestation_policy_digest_missing",
                      attestation=attestation(policy_digest=digest))

    def test_denies_attestation_from_a_different_policy(self):
        self.deny("attestation_policy_digest_mismatch",
                  request=request(policy_digest="sha256:" + "f" * 64))

    def test_denies_stale_attestation_sha(self):
        self.deny("attestation_stale_source_sha", attestation=attestation(source_sha="f" * 40))

    def test_denies_failing_tests(self):
        self.deny("attestation_tests_failed",
                  attestation=attestation(tests=[{"command": "pytest", "exit": 1}]))

    def test_denies_missing_tests(self):
        self.deny("attestation_tests_missing", attestation=attestation(tests=[]))

    def test_denies_first_party_changes_outside_the_service(self):
        self.deny("changed_paths_outside_service",
                  attestation=attestation(changed_paths=["paperclip-mcp/gitops/auto-release.py"]))

    def test_denies_path_traversal_in_changed_paths(self):
        self.deny("changed_paths_outside_service",
                  attestation=attestation(changed_paths=["mcp/mantic-mcp/../paperclip-mcp/x.py"]))

    def test_denies_absolute_changed_path(self):
        self.deny("changed_paths_outside_service",
                  attestation=attestation(changed_paths=["/etc/passwd"]))

    def test_denies_unreviewed_tree_as_source(self):
        # A squash merge makes the merged main SHA the source SHA; anything else
        # means an unreviewed tree would be built and shipped.
        self.deny("source_sha_not_merged_source",
                  request=request(merge_sha="a" * 39 + "b"))

    def test_denies_unauthorized_release_branch(self):
        self.deny("unauthorized_release_branch", request=request(base_ref="ci-approved"))

    def test_denies_image_digest_mismatch(self):
        self.deny("image_digest_mismatch", request=request(image_digest="sha256:" + "e" * 64))

    def test_denies_manifest_without_review_gate(self):
        broken = manifest()
        broken["other_resources"][0]["exact_sha_required"] = False
        self.deny("manifest_review_gate_missing", manifest=broken)

    def test_accepts_other_resources_exact_source_vocabulary(self):
        # other_resources[] express the same gate as
        # source_commit_required_when_source_built + exact_image_digest_required.
        alt = manifest()
        entry = alt["other_resources"][0]
        entry.pop("exact_sha_required")
        entry["source_commit_required_when_source_built"] = True
        entry["exact_image_digest_required"] = True
        self.assertTrue(gate.evaluate(alt, request(), grant=grant(), attestation=attestation(),
                                      now=NOW, expected_source_sha=SOURCE)["admit"])

    def test_denies_manifest_with_weakened_digest_gate(self):
        broken = manifest()
        broken["other_resources"][0]["exact_image_digest_required"] = False
        self.deny("manifest_review_gate_missing", manifest=broken)

    def test_denies_valid_service_under_foreign_repository(self):
        foreign = manifest()
        foreign["other_resources"][0]["repository"] = "miloszspyrka-code/zar-i-szlif"
        self.deny("service_not_in_harness_repository", manifest=foreign)

    def test_real_repo_manifest_holds_or_auto_deploys_every_mcp_service(self):
        data = json.loads(Path("ops/release-lanes.json").read_text(encoding="utf-8"))
        entries = {e["id"]: e for e in data["lanes"] + data["other_resources"]}
        auto = {"emailens-mcp", "mantic-mcp", "plasmic-mcp",
                "playwright-mcp", "supabase-mcp", "ubuntu-mcp"}
        mcp = auto | {"paperclip-mcp"}
        self.assertTrue(mcp.issubset(entries), "MCP services must stay in the release manifest")
        for service in sorted(mcp):
            entry = entries[service]
            if service in auto:
                self.assertEqual(entry.get("promotion_state"), "auto_main", service)
                self.assertIs(entry.get("auto_deploy_expected"), True, service)
                continue
            self.assertEqual(entry.get("promotion_state", "hold"), "hold",
                             service + " must stay on hold in ops/release-lanes.json")
            with self.assertRaises(gate.Denied) as caught:
                gate.evaluate(data, request(service=service, coolify_uuid=entry["coolify_uuid"],
                                            coolify_kind=entry["coolify_kind"]),
                              attestation=attestation(service=service), now=NOW, expected_source_sha=SOURCE)
            self.assertEqual(str(caught.exception), "release_lane_on_hold")

    def test_denial_returns_no_admission_record(self):
        with self.assertRaises(gate.Denied):
            gate.evaluate(manifest(), request(), grant=None, attestation=attestation(), now=NOW, expected_source_sha=SOURCE)
        self.assertFalse(hasattr(gate, "promote") or hasattr(gate, "deploy"),
                         "admission gate must expose no promotion/deploy action")


class BuildStageAdmissionTests(unittest.TestCase):
    """`evaluate_build` authorizes the build stage only, never a deploy."""

    def test_admits_a_build_without_an_attestation(self):
        record = gate.evaluate_build(manifest(promotion_state="approved"), request(),
                                     grant=grant(), now=NOW, expected_source_sha=SOURCE)
        self.assertTrue(record["admit_build"])
        self.assertNotIn("image_digest", record)

    def test_denies_held_lane_without_grant(self):
        with self.assertRaises(gate.Denied) as caught:
            gate.evaluate_build(manifest(), request(), grant=None, now=NOW, expected_source_sha=SOURCE)
        self.assertEqual(str(caught.exception), "release_lane_on_hold")

    def test_denies_expired_grant(self):
        with self.assertRaises(gate.Denied) as caught:
            gate.evaluate_build(manifest(promotion_state="approved"), request(),
                                grant=grant(expires_at=(NOW - timedelta(minutes=1)).isoformat()),
                                now=NOW, expected_source_sha=SOURCE)
        self.assertEqual(str(caught.exception), "grant_expired")

    def test_denies_self_review(self):
        approval = request()["approval"] | {"reviewer_agent_id": "producer-agent"}
        with self.assertRaises(gate.Denied) as caught:
            gate.evaluate_build(manifest(promotion_state="approved"), request(approval=approval),
                                grant=grant(), now=NOW, expected_source_sha=SOURCE)
        self.assertEqual(str(caught.exception), "self_review_forbidden")

    def test_build_admission_is_not_deploy_admission(self):
        # The same inputs that allow a build still cannot deploy: only the full
        # evaluation demands the root-owned attestation and immutable digest.
        man, req, gr = manifest(promotion_state="approved"), request(), grant()
        self.assertTrue(gate.evaluate_build(man, req, grant=gr, now=NOW, expected_source_sha=SOURCE)["admit_build"])
        with self.assertRaises(gate.Denied) as caught:
            gate.evaluate(man, req, grant=gr, attestation=None, now=NOW, expected_source_sha=SOURCE)
        self.assertEqual(str(caught.exception), "local_ci_attestation_missing")

    def test_denies_build_evidence_bound_to_another_source_sha(self):
        # CTO finding on d3f4055: a request/grant for SHA A must not admit a
        # build of SHA B. The build's SHA is now an argument, not a claim.
        with self.assertRaises(gate.Denied) as caught:
            gate.evaluate_build(manifest(promotion_state="approved"), request(), grant=grant(),
                                now=NOW, expected_source_sha="9" * 40)
        self.assertEqual(str(caught.exception), "admission_source_sha_mismatch")

    def test_denies_release_evidence_bound_to_another_source_sha(self):
        with self.assertRaises(gate.Denied) as caught:
            gate.evaluate(manifest(), request(), grant=grant(), attestation=attestation(),
                          now=NOW, expected_source_sha="9" * 40)
        self.assertEqual(str(caught.exception), "admission_source_sha_mismatch")

    def test_denies_an_invalid_promoted_source_sha(self):
        for value in (None, "", "xyz", "a" * 39, "A" * 40):
            with self.assertRaises(gate.Denied) as caught:
                gate.evaluate_build(manifest(promotion_state="approved"), request(), grant=grant(),
                                    now=NOW, expected_source_sha=value)
            self.assertEqual(str(caught.exception), "invalid_expected_source_sha")

    def test_the_sha_binding_cannot_be_omitted(self):
        # Keyword-only and without a default: a caller cannot silently skip the
        # binding, which is how the d3f4055 delivery path admitted SHA B.
        with self.assertRaises(TypeError):
            gate.evaluate_build(manifest(promotion_state="approved"), request(), grant=grant())
        with self.assertRaises(TypeError):
            gate.evaluate(manifest(), request(), grant=grant(), attestation=attestation())


class AttestationVerificationTests(unittest.TestCase):
    """The delivery path must verify the HMAC; a claimed flag is never proof."""

    KEY = b"k" * 32

    def signed(self):
        import harness_local_ci_attest as attester

        return attester.build_attestation(
            "mantic-mcp", SOURCE, [{"command": "true", "exit": 0}],
            ["mcp/mantic-mcp/src/server.ts"], DIGEST, self.KEY, runner_uid=1000,
            policy_digest=attestation()["policy_digest"])

    def test_a_verified_attestation_is_admitted(self):
        record = gate.evaluate(manifest(), request(), grant=grant(),
                               attestation=gate.verified_attestation(self.signed(), self.KEY),
                               now=NOW, expected_source_sha=SOURCE)
        self.assertTrue(record["admit"])
        self.assertEqual(record["image_digest"], DIGEST)

    def test_a_forged_signature_verified_flag_is_not_evidence(self):
        # Exactly the CTO finding: raw JSON claiming signature_verified=true.
        forged = dict(attestation())
        self.assertIs(forged["signature_verified"], True)
        with self.assertRaises(gate.Denied) as caught:
            gate.evaluate(manifest(), request(), grant=grant(), attestation=forged,
                          now=NOW, expected_source_sha=SOURCE)
        self.assertEqual(str(caught.exception), "attestation_signature_unverified")

    def test_a_signature_from_another_key_is_refused(self):
        with self.assertRaises(gate.Denied) as caught:
            gate.verified_attestation(self.signed(), b"z" * 32)
        self.assertEqual(str(caught.exception), "attestation_signature_invalid")

    def test_a_tampered_field_breaks_the_signature(self):
        tampered = self.signed()
        tampered["tests"] = [{"command": "true", "exit": 0}]
        tampered["image_digest"] = "sha256:" + "7" * 64
        with self.assertRaises(gate.Denied) as caught:
            gate.verified_attestation(tampered, self.KEY)
        self.assertEqual(str(caught.exception), "attestation_signature_invalid")

    def test_a_verified_attestation_still_cannot_switch_source_sha(self):
        verified = gate.verified_attestation(self.signed(), self.KEY)
        with self.assertRaises(gate.Denied) as caught:
            gate.evaluate(manifest(), request(), grant=grant(), attestation=verified,
                          now=NOW, expected_source_sha="f" * 40)
        self.assertEqual(str(caught.exception), "admission_source_sha_mismatch")


class CliBindingTests(unittest.TestCase):
    """The operator CLI applies the same binding as the library."""

    def test_cli_requires_the_promoted_source_sha(self):
        with self.assertRaises(SystemExit):
            gate.main(["--manifest", "m", "--request", "r"])

    def test_cli_denies_a_source_sha_that_differs_from_the_request(self):
        documents = {"manifest": manifest(promotion_state="approved"),
                     "request": request(), "grant": grant()}
        stderr = io.StringIO()
        with patch.object(gate, "load_gate_file",
                          side_effect=lambda path, label, require_root=False: dict(documents[label])), \
                patch("sys.stdout", io.StringIO()), patch("sys.stderr", stderr):
            code = gate.main(["--manifest", "m", "--request", "r", "--grant", "g",
                              "--source-sha", "9" * 40])
        self.assertEqual(code, 1)
        self.assertIn("admission_source_sha_mismatch", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
