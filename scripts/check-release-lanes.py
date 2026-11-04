#!/usr/bin/env python3
"""Structural release contract and fail-closed negative cases; NOT live deployment proof."""
import argparse
import copy
import json
from pathlib import Path

def check(data):
    def must(ok, message):
        if not ok:
            raise ValueError(message)
    must(data.get("schema_version") == 1 and data.get("owner") == "CHO", "schema/owner")
    lanes, other, workers = data.get("lanes"), data.get("other_resources"), data.get("cloudflare_workers")
    snap = data.get("scope_snapshot", {})
    must(all(isinstance(x, list) and len(x) for x in (lanes, other, workers)), "incomplete inventory arrays")
    must(snap.get("coolify_applications") == 4 and snap.get("coolify_services") == 26 and snap.get("coolify_total") == 30, "incomplete Coolify snapshot")
    must(snap.get("cloudflare_workers") == 3 == len(workers), "incomplete Workers snapshot")
    allowed = {"git_promoted", "git_canary_manual", "manual_pinned", "upstream_pinned"}
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
        must(bool(lane.get("observed_baseline")), f"{name}: missing observed baseline")
        if lane["mode"] == "git_promoted":
            must(lane["environment"] == "production", "canary cannot be promoted")
            must(all(lane.get(k) for k in ("integration_ref", "release_ref", "ci_workflow", "production_readback")), f"{name}: incomplete git promotion")
            must(lane["integration_ref"] != lane["release_ref"], f"{name}: integration branch deployed directly")
        elif lane["mode"] == "git_canary_manual":
            must(lane["environment"] == "canary" and lane.get("auto_deploy_expected") is False and bool(lane.get("candidate_ref")), f"{name}: unsafe canary")
        else:
            must(lane.get("auto_deploy_expected") is False, f"{name}: pinned image autopromotes")
    for r in other:
        name, uuid, kind = r.get("id"), r.get("coolify_uuid"), r.get("coolify_kind")
        must(bool(name) and isinstance(uuid, str) and uuid not in uuids and len(uuid) >= 12, f"missing/duplicate resource: {name}")
        must(r.get("platform") == "coolify" and kind in counts, f"{name}: wrong platform/kind")
        must(r.get("release_route") in ("coolify_reviewed_digest_manual", "inactive_no_promotion"), f"{name}: unsafe release route")
        must(r.get("promotion_state") == "hold" and r.get("evidence_state") == "open", f"{name}: false attestation")
        must(r.get("auto_deploy_expected") is False and r.get("review_required") is True, f"{name}: unreviewed/automatic release")
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
        must(w.get("source_provenance_verified") is False, f"{name}: invented source provenance")
        must(all(w.get(k) for k in ("deployment_id", "version_id", "deployment_at", "release_contract")), f"{name}: missing Worker version/rollback route")
    must(names == {"paperclip-mcp", "stronaglowna", "zariszlif-prawne"}, "existing Worker lost")
    must("product-panel" in ids, "product release lane absent")
    core = next((x for x in lanes if x["id"] == "paperclip-core"), None)
    must(core is not None and core.get("repository") == "paperclipai/paperclip" and core.get("artifact_source_ref") == "ghcr.io/paperclipai/paperclip:2026.1023.0", "upstream Paperclip identity incorrect")
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
    print("PASS: 11 fail-closed structural regressions (not live deploy/rollback tests)")

if __name__ == "__main__":
    arg = argparse.ArgumentParser()
    arg.add_argument("--self-test", action="store_true")
    options = arg.parse_args()
    manifest = json.loads(Path("ops/release-lanes.json").read_text(encoding="utf-8"))
    a, b, c = check(manifest)
    print(f"PASS: {a} release lanes + {b} Coolify hold/inactive resources + {c} existing Workers (dated structural inventory)")
    if options.self_test:
        negative_cases(manifest)
