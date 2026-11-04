#!/usr/bin/env python3
"""Structural validation only; does not claim live release/readback proof."""
import json
from pathlib import Path

data = json.loads(Path("ops/release-lanes.json").read_text(encoding="utf-8"))
assert data.get("schema_version") == 1
assert data.get("owner") == "CHO"
lanes = data.get("lanes")
assert isinstance(lanes, list) and lanes, "release lanes missing"
ids, uuids = set(), set()
allowed = {"git_promoted", "git_canary_manual", "manual_pinned", "upstream_pinned"}
for lane in lanes:
    name = lane.get("id")
    assert isinstance(name, str) and name and name not in ids, f"duplicate/empty id: {name}"
    ids.add(name)
    uuid = lane.get("coolify_uuid")
    assert isinstance(uuid, str) and len(uuid) >= 12 and uuid not in uuids, f"{name}: duplicate/missing Coolify uuid"
    uuids.add(uuid)
    assert lane.get("coolify_kind") in ("application", "service"), f"{name}: missing Coolify kind"
    assert lane.get("environment") in ("canary", "production"), f"{name}: invalid environment"
    assert lane.get("mode") in allowed, f"{name}: invalid release mode"
    assert isinstance(lane.get("repository"), str) and "/" in lane["repository"], f"{name}: missing repo/provenance"
    assert lane.get("exact_sha_required") is True, f"{name}: exact immutable provenance gate required"
    assert lane.get("review_required") is True, f"{name}: review gate required"
    assert isinstance(lane.get("observed_baseline"), str), f"{name}: mark observed baseline"
    if lane["mode"] == "git_promoted":
        assert lane["environment"] == "production"
        assert all(lane.get(field) for field in ("integration_ref", "release_ref", "ci_workflow", "production_readback")), f"{name}: missing promote contract"
        assert lane["integration_ref"] != lane["release_ref"], f"{name}: release ref cannot be integration ref"
    if lane["mode"] == "git_canary_manual":
        assert lane["environment"] == "canary", f"{name}: canary cannot be production"
        assert lane.get("auto_deploy_expected") is False, f"{name}: canary auto-deploy must stay off"
        assert lane.get("candidate_ref"), f"{name}: candidate ref required"
    if lane["mode"] in ("manual_pinned", "upstream_pinned"):
        assert lane.get("auto_deploy_expected") is False, f"{name}: pinned release needs explicit approval"
assert "product-panel" in ids, "verified product lane required"
print(f"PASS: validated {len(lanes)} release lanes (structure only; live deploy proof is separate)")
