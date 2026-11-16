"""Fail-closed tests for the Harness MCP release admission gate (ZARI-240).

Every negative case below is the control for a way an unreviewed or held merge
could otherwise reach Coolify. A denial is the admission gate's only output in
that case, so no image is promoted and the previously running image stays
untouched; the controller must never see an admission record to act on.
"""
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
        "service": "mantic-mcp",
        "source_sha": SOURCE,
        "image_digest": DIGEST,
        "tests": [{"command": "python -m pytest -q", "exit": 0}],
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


class AdmissionTests(unittest.TestCase):
    def deny(self, reason, **kwargs):
        kwargs.setdefault("grant", grant())
        kwargs.setdefault("attestation", attestation())
        with self.assertRaises(gate.Denied) as caught:
            gate.evaluate(kwargs.pop("manifest", manifest()), kwargs.pop("request", request()),
                          now=kwargs.pop("now", NOW), **kwargs)
        self.assertEqual(str(caught.exception), reason)

    def test_admits_fully_evidenced_promotion(self):
        record = gate.evaluate(manifest(), request(), grant=grant(), attestation=attestation(), now=NOW)
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
                  attestation=attestation(changed_paths=["mantic-mcp/../paperclip-mcp/x.py"]))

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
                                      now=NOW)["admit"])

    def test_denies_manifest_with_weakened_digest_gate(self):
        broken = manifest()
        broken["other_resources"][0]["exact_image_digest_required"] = False
        self.deny("manifest_review_gate_missing", manifest=broken)

    def test_denies_valid_service_under_foreign_repository(self):
        foreign = manifest()
        foreign["other_resources"][0]["repository"] = "miloszspyrka-code/zar-i-szlif"
        self.deny("service_not_in_harness_repository", manifest=foreign)

    def test_real_repo_manifest_holds_every_mcp_service(self):
        data = json.loads(Path("ops/release-lanes.json").read_text(encoding="utf-8"))
        entries = {e["id"]: e for e in data["lanes"] + data["other_resources"]}
        mcp = {"mantic-mcp", "plasmic-mcp", "playwright-mcp", "supabase-mcp", "paperclip-mcp"}
        self.assertTrue(mcp.issubset(entries), "MCP services must stay in the release manifest")
        for service in sorted(mcp):
            entry = entries[service]
            # Hold-by-default: an explicit "hold" or an absent promotion_state.
            self.assertIn(entry.get("promotion_state", "hold"), ("hold",),
                          service + " must stay on hold in ops/release-lanes.json")
            with self.assertRaises(gate.Denied) as caught:
                gate.evaluate(data, request(service=service, coolify_uuid=entry["coolify_uuid"],
                                            coolify_kind=entry["coolify_kind"]),
                              attestation=attestation(service=service), now=NOW)
            self.assertEqual(str(caught.exception), "release_lane_on_hold")

    def test_denial_returns_no_admission_record(self):
        with self.assertRaises(gate.Denied):
            gate.evaluate(manifest(), request(), grant=None, attestation=attestation(), now=NOW)
        self.assertFalse(hasattr(gate, "promote") or hasattr(gate, "deploy"),
                         "admission gate must expose no promotion/deploy action")


if __name__ == "__main__":
    unittest.main()
