#!/usr/bin/env python3
"""Structural release contract and fail-closed negative cases; NOT live deployment proof."""
import argparse
import copy
import json
import re
from pathlib import Path

def check(data):
    def must(ok, message):
        if not ok:
            raise ValueError(message)
    must(data.get("schema_version") == 1 and data.get("owner") == "CHO", "schema/owner")
    lanes, other, workers = data.get("lanes"), data.get("other_resources"), data.get("cloudflare_workers")
    snap = data.get("scope_snapshot", {})
    must(all(isinstance(x, list) and len(x) for x in (lanes, other, workers)), "incomplete inventory arrays")
    must(snap.get("coolify_applications") == 5 and snap.get("coolify_services") == 26 and snap.get("coolify_total") == 31, "incomplete Coolify snapshot")
    must(snap.get("cloudflare_workers") == 3 == len(workers), "incomplete Workers snapshot")
    allowed = {"git_promoted", "git_canary_manual", "git_canary_auto", "manual_pinned", "upstream_pinned"}
    ids, uuids, counts = set(), set(), {"application": 0, "service": 0}
    for lane in lanes:
        name, uuid = lane.get("id"), lane.get("coolify_uuid")
        must(bool(name) and name not in ids, f"duplicate/missing lane id: {name}")
        must(isinstance(uuid, str) and len(uuid) >= 12 and uuid not in uuids, f"duplicate/missing Coolify UUID: {name}")
        ids.add(name)
        uuids.add(uuid)
        kind = lane.get("coolify_kind")
        must(kind in counts, f"{name}: wrong kind")
        counts[kind] += 1
        must(lane.get("environment") in ("canary", "production"), f"{name}: invalid environment")
        must(lane.get("mode") in allowed, f"{name}: wrong mode")
        must(isinstance(lane.get("repository"), str) and "/" in lane["repository"], f"{name}: source missing")
        must(lane.get("review_required") is True and lane.get("exact_sha_required") is True, f"{name}: missing review/provenance gate")
        expected_reviewer = "CTO" if lane["repository"] == "miloszspyrka-code/zar-i-szlif" else "CHO"
        must(lane.get("reviewer_role") == expected_reviewer, f"{name}: wrong review owner")
        must(bool(lane.get("observed_baseline")), f"{name}: missing observed baseline")
        if lane["mode"] == "git_promoted":
            must(lane["environment"] == "production", "canary cannot be promoted")
            must(all(lane.get(k) for k in ("integration_ref", "release_ref", "ci_workflow", "production_readback")), f"{name}: incomplete git promotion")
            must(lane["integration_ref"] != lane["release_ref"], f"{name}: integration branch deployed directly")
        elif lane["mode"] == "git_canary_manual":
            must(lane["environment"] == "canary" and lane.get("auto_deploy_expected") is False and bool(lane.get("candidate_ref")), f"{name}: unsafe canary")
        elif lane["mode"] == "git_canary_auto":
            must(lane["environment"] == "canary" and lane.get("auto_deploy_expected") is True, f"{name}: wrong auto canary")
            must(bool(lane.get("candidate_ref")) and lane.get("production_auto_promotion") is False, f"{name}: must not auto promote to prod")
            must(lane.get("observed_no_public_host_ports") is True and lane.get("network_isolation_verified") is False, f"{name}: unsupported isolation claim")
        else:
            must(lane.get("auto_deploy_expected") is False, f"{name}: pinned image autopromotes")
    auto_main_services = {
        "emailens-mcp", "mantic-mcp", "plasmic-mcp",
        "playwright-mcp", "supabase-mcp", "ubuntu-mcp",
    }
    for r in other:
        name, uuid, kind = r.get("id"), r.get("coolify_uuid"), r.get("coolify_kind")
        must(bool(name) and isinstance(uuid, str) and uuid not in uuids and len(uuid) >= 12, f"missing/duplicate resource: {name}")
        must(r.get("platform") == "coolify" and kind in counts, f"{name}: wrong platform/kind")
        route = r.get("release_route")
        must(route in ("coolify_reviewed_digest_manual", "inactive_no_promotion",
                       "coolify_auto_main_digest"), f"{name}: unsafe release route")
        if route == "coolify_auto_main_digest":
            # Explicit, reviewed automatic lane: merge to trusted main is the
            # release authorization; exact source/digest/health/rollback remain.
            must(name in auto_main_services, f"{name}: auto lane not allowlisted")
            must(r.get("promotion_state") == "auto_main", f"{name}: auto lane not declared")
            must(r.get("auto_deploy_expected") is True, f"{name}: auto lane not automatic")
            must(r.get("review_required") is True, f"{name}: auto lane lost review policy")
            must(r.get("reviewer_role") == "CHO" and "CHO + CTO" not in str(r.get("release_contract", "")), f"{name}: duplicate/wrong Harness review")
            must(r.get("exact_image_digest_required") is True and r.get("source_commit_required_when_source_built") is True, f"{name}: source/digest mismatch unguarded")
        else:
            must(r.get("promotion_state") == "hold" and r.get("evidence_state") == "open", f"{name}: false attestation")
            must(r.get("auto_deploy_expected") is False and r.get("review_required") is True, f"{name}: unreviewed/automatic release")
            must(r.get("reviewer_role") == "CHO" and "CHO + CTO" not in str(r.get("release_contract", "")), f"{name}: duplicate/wrong Harness review")
            must(r.get("exact_image_digest_required") is True and r.get("source_commit_required_when_source_built") is True, f"{name}: source/digest mismatch unguarded")
        must(all(r.get(k) for k in ("observed_status", "observed_image_ref", "release_contract")), f"{name}: missing evidence/contract")
        uuids.add(uuid)
        counts[kind] += 1
    must(counts == {"application": snap["coolify_applications"], "service": snap["coolify_services"]}, f"Coolify coverage: {counts}")
    must(len(uuids) == snap["coolify_total"], "Coolify UUID coverage")
    names = set()
    for w in workers:
        name = w.get("id")
        must(bool(name) and name not in names and w.get("platform") == "cloudflare-workers", "Worker missing/duplicate")
        names.add(name)
        must(w.get("release_route") == "cloudflare_reviewed_version_manual", f"{name}: unsafe Worker release")
        must(w.get("promotion_state") == "hold" and w.get("auto_deploy_expected") is False and w.get("review_required") is True, f"{name}: unsafe Worker promotion")
        must(w.get("reviewer_role") == "CHO", f"{name}: wrong Worker release reviewer")
        must(w.get("source_provenance_verified") is False, f"{name}: invented source provenance")
        must(all(w.get(k) for k in ("deployment_id", "version_id", "deployment_at", "release_contract")), f"{name}: missing Worker version/rollback route")
    must(names == {"paperclip-mcp", "stronaglowna", "zariszlif-prawne"}, "existing Worker lost")
    must("product-panel" in ids, "product release lane absent")
    core = next((x for x in lanes if x["id"] == "paperclip-core"), None)
    must(core is not None and core.get("repository") == "miloszspyrka-code/harness-zar-i-szlif" and core.get("upstream_base_repository") == "paperclipai/paperclip" and core.get("upstream_base_ref") == "ghcr.io/paperclipai/paperclip:2026.1023.0", "upstream Paperclip identity incorrect")
    must(re.fullmatch(r"[0-9a-f]{40}", str(core.get("overlay_source_sha", ""))) is not None, "missing immutable Core overlay SHA")
    must(re.fullmatch(r"sha256:[0-9a-f]{64}", str(core.get("runtime_image_id", ""))) is not None, "missing immutable Core runtime image digest")
    must(str(core.get("artifact_source_ref", "")).startswith("local/paperclip-core-h03-candidate:"), "Paperclip Core runtime source reference incorrect")
    must(core.get("overlay_source_to_runtime_digest_verified") is False, "unverified source/digest attestation claimed")
    return len(lanes), len(other), len(workers)

def negative_cases(manifest):
    def reject(label, edit):
        x = copy.deepcopy(manifest)
        edit(x)
        try:
            check(x)
        except (ValueError, KeyError, TypeError):
            return
        raise RuntimeError(f"FAIL OPEN: {label} incorrectly accepted")
    reject("missing-Coolify-service", lambda x: x["other_resources"].pop())
    reject("duplicate-UUID", lambda x: x["other_resources"][0].update(coolify_uuid=x["lanes"][0]["coolify_uuid"]))
    reject("unreviewed-image-release", lambda x: x["other_resources"][0].update(review_required=False))
    reject("automatic-unproved-image-release", lambda x: x["other_resources"][0].update(auto_deploy_expected=True))
    reject("false-approved-state", lambda x: x["other_resources"][0].update(promotion_state="approved"))
    reject("missing-source-gate", lambda x: x["other_resources"][0].update(source_commit_required_when_source_built=False))
    reject("production-direct-integration-ref", lambda x: x["lanes"][0].update(release_ref=x["lanes"][0]["integration_ref"]))
    reject("unverified-Worker-promoted", lambda x: x["cloudflare_workers"][0].update(promotion_state="approved"))
    reject("missing-Worker", lambda x: x["cloudflare_workers"].pop())
    reject("invented-Worker-source", lambda x: x["cloudflare_workers"][0].update(source_provenance_verified=True))
    reject("wrong-upstream-repo", lambda x: next(a for a in x["lanes"] if a["id"] == "paperclip-core").update(repository="miloszspyrka-code/paperclip"))
    reject("auto-canary-to-production", lambda x: next(a for a in x["lanes"] if a["id"] == "hermes-gateway-git-release-candidate").update(production_auto_promotion=True))
    reject("false-overlay-source-attestation", lambda x: next(a for a in x["lanes"] if a["id"] == "paperclip-core").update(overlay_source_to_runtime_digest_verified=True))
    reject("wrong-product-reviewer", lambda x: next(a for a in x["lanes"] if a["id"] == "product-panel").update(reviewer_role="CHO"))
    reject("wrong-harness-reviewer", lambda x: next(a for a in x["lanes"] if a["id"] == "paperclip-mcp").update(reviewer_role="CTO"))
    reject("duplicate-reviewers-for-manual-MCP", lambda x: next(a for a in x["other_resources"] if a["id"] == "opik-mcp").update(release_contract="CHO + CTO approved digest"))
    print("PASS: 16 fail-closed structural regressions (not live deploy/rollback tests)")

if __name__ == "__main__":
    arg = argparse.ArgumentParser()
    arg.add_argument("--self-test", action="store_true")
    options = arg.parse_args()
    manifest = json.loads(Path("ops/release-lanes.json").read_text(encoding="utf-8"))
    a, b, c = check(manifest)
    print(f"PASS: {a} release lanes + {b} Coolify hold/inactive resources + {c} existing Workers (dated structural inventory)")
    if options.self_test:
        negative_cases(manifest)

    # Use the already-enabled release-lanes-policy workflow. The GitHub App
    # cannot create/update a new .github/workflows file without workflows scope.
    # These checks run in the existing workflow's --self-test invocation.
    from check_service_coverage import check as check_service_coverage
    from unittest import TestLoader, TextTestRunner
    classified, targeted = check_service_coverage()
    print(f"PASS: {classified} root folders classified, {targeted} targeted CI roots")
    if options.self_test:
        suite = TestLoader().discover("scripts", pattern="test_check_service_coverage.py")
        # ZARI-240: the fail-closed release admission gate and the root-invoked
        # local-CI attester must run in the same PR-time lane as the structural
        # release contract, so a hold/attestation regression cannot merge.
        for pattern in ("test_harness_release_admission.py", "test_harness_local_ci_attest.py",
                        "test_harness_delivery_controller.py", "test_harness_native_delivery.py",
                        "test_harness_install_preflight.py", "test_harness_release_parity.py"):
            suite.addTests(TestLoader().discover("scripts", pattern=pattern))
        result = TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful():
            raise SystemExit(1)
