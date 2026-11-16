#!/usr/bin/env python3
"""Fail-closed release admission for Harness MCP services (ZARI-240).

The root-owned Harness delivery controller MUST call :func:`evaluate` (or this
module's CLI) before any image promotion or Coolify deployment. A merged pull
request is never admission on its own: the ``ops/release-lanes.json`` hold, the
independent exact-SHA review, the root-owned local-CI attestation, the revocable
per-UUID operator grant and the immutable source SHA are each required
independently. Any missing, stale, ambiguous, expired or inconsistent input
denies the release, so an unreviewed or held merge can never promote an image
and the previously running image stays intact.

This module is read-only: it never builds, promotes, deploys or mutates any
provider, and it deliberately exposes no ``--force``/``--skip``/override flag.
Hold is the default: a resource without an explicit ``promotion_state`` is held,
and no manifest edit can substitute for a per-UUID grant.
"""
import argparse
import json
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = "miloszspyrka-code/harness-zar-i-szlif"
RELEASE_BASE_REF = "main"
MANIFEST_SCHEMA = 1
ATTESTATION_SCHEMA = 1
GRANT_SCHEMA = 1
HELD = "hold"

SERVICE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
SHA = re.compile(r"[a-f0-9]{40}\Z")
DIGEST = re.compile(r"sha256:[a-f0-9]{64}\Z")
COOLIFY_UUID = re.compile(r"[a-z0-9]{20,32}\Z")


class Denied(Exception):
    """Non-admissible release. The message is a stable audit reason code."""


def _text(value):
    return isinstance(value, str) and 0 < len(value) <= 200


def parse_time(value):
    """Parse an ISO-8601 timestamp; naive values are read as UTC."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        raise Denied("timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise Denied("timestamp_invalid") from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def manifest_entry(manifest, service):
    """Resolve exactly one harness-owned Coolify entry for ``service``."""
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise Denied("manifest_schema_invalid")
    if not isinstance(service, str) or not SERVICE_ID.fullmatch(service):
        raise Denied("invalid_service_id")
    entries = (manifest.get("lanes") or []) + (manifest.get("other_resources") or [])
    matched = [e for e in entries if isinstance(e, dict) and e.get("id") == service]
    if not matched:
        raise Denied("unknown_service")
    if len(matched) != 1:
        raise Denied("ambiguous_service")
    entry = matched[0]
    if entry.get("platform", "coolify") != "coolify":
        raise Denied("unsupported_platform")
    if "repository" in entry and entry.get("repository") != REPO:
        raise Denied("service_not_in_harness_repository")
    if entry.get("review_required") is not True:
        raise Denied("manifest_review_gate_missing")
    # lanes[] declare `exact_sha_required`; other_resources[] declare the
    # equivalent `source_commit_required_when_source_built`. A harness resource
    # must carry at least one exact-source gate and must never weaken an
    # explicit immutable-digest requirement.
    if not (entry.get("exact_sha_required") is True
            or entry.get("source_commit_required_when_source_built") is True):
        raise Denied("manifest_review_gate_missing")
    if entry.get("exact_image_digest_required") is False:
        raise Denied("manifest_review_gate_missing")
    return entry


def _require_sha(value, reason):
    if not (isinstance(value, str) and SHA.fullmatch(value)):
        raise Denied(reason)
    return value


def _check_review(entry, request):
    approval = request.get("approval")
    if not isinstance(approval, dict):
        raise Denied("independent_review_missing")
    reviewer = approval.get("reviewer_agent_id")
    producer = approval.get("producer_agent_id")
    if not (_text(reviewer) and _text(producer)):
        raise Denied("review_identity_missing")
    if reviewer == producer:
        raise Denied("self_review_forbidden")
    if approval.get("reviewer_role") != entry.get("reviewer_role"):
        raise Denied("wrong_reviewer_role")
    approved_sha = _require_sha(approval.get("approved_sha"), "invalid_approved_sha")
    head_sha = _require_sha(request.get("head_sha"), "invalid_head_sha")
    # Reviewer approval is bound to the immutable PR head. A later push, rebase
    # or different commit invalidates it instead of inheriting approval.
    if approved_sha != head_sha:
        raise Denied("pr_head_changed_after_review")
    return reviewer, head_sha


def _check_attestation(entry, request, attestation, source_sha):
    if not isinstance(attestation, dict):
        raise Denied("local_ci_attestation_missing")
    if attestation.get("schema_version") != ATTESTATION_SCHEMA:
        raise Denied("attestation_schema_invalid")
    # Set only by a verifying caller after HMAC/provenance validation; a raw
    # JSON file can never assert its own authenticity.
    if attestation.get("signature_verified") is not True:
        raise Denied("attestation_signature_unverified")
    if attestation.get("attestor_uid") != 0:
        raise Denied("attestation_not_root_owned")
    # Owner security finding on PR #112: an attestation whose tests ran as root
    # (or without a recorded unprivileged runner) proves nothing about a safe
    # release, so it is refused rather than trusted.
    runner_uid = attestation.get("runner_uid")
    if not isinstance(runner_uid, int) or isinstance(runner_uid, bool) or runner_uid <= 0:
        raise Denied("attestation_test_runner_not_privilege_dropped")
    policy_digest = attestation.get("policy_digest")
    if not (isinstance(policy_digest, str) and DIGEST.fullmatch(policy_digest)):
        raise Denied("attestation_policy_digest_missing")
    if request.get("policy_digest") is not None and request["policy_digest"] != policy_digest:
        raise Denied("attestation_policy_digest_mismatch")
    if attestation.get("service") != entry.get("id"):
        raise Denied("attestation_service_mismatch")
    if attestation.get("source_sha") != source_sha:
        raise Denied("attestation_stale_source_sha")
    results = attestation.get("tests")
    if not isinstance(results, list) or not results:
        raise Denied("attestation_tests_missing")
    for record in results:
        if not isinstance(record, dict) or not _text(record.get("command")):
            raise Denied("attestation_test_record_invalid")
        exit_code = record.get("exit")
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            raise Denied("attestation_test_record_invalid")
        if exit_code != 0:
            raise Denied("attestation_tests_failed")
    changed = attestation.get("changed_paths")
    if not isinstance(changed, list) or not changed:
        raise Denied("attestation_changed_paths_missing")
    prefix = entry["id"] + "/"
    for path in changed:
        if not _text(path) or path.startswith("/") or "/../" in path or not path.startswith(prefix):
            raise Denied("changed_paths_outside_service")
    digest = attestation.get("image_digest")
    if not (isinstance(digest, str) and DIGEST.fullmatch(digest)):
        raise Denied("image_digest_missing")
    if request.get("image_digest") != digest:
        raise Denied("image_digest_mismatch")
    return digest


def _check_grant(entry, request, grant, source_sha, now):
    """A revocable, audited per-UUID promotion grant is mandatory to deploy."""
    if not isinstance(grant, dict):
        raise Denied("per_uuid_grant_missing")
    if grant.get("schema_version") != GRANT_SCHEMA:
        raise Denied("grant_schema_invalid")
    if grant.get("revoked") is not False:
        raise Denied("grant_revoked")
    if grant.get("coolify_uuid") != request.get("coolify_uuid"):
        raise Denied("grant_uuid_mismatch")
    if grant.get("service") != entry.get("id"):
        raise Denied("grant_service_mismatch")
    if grant.get("source_sha") != source_sha:
        raise Denied("grant_source_sha_mismatch")
    if not (_text(grant.get("grant_id")) and _text(grant.get("granted_by"))):
        raise Denied("grant_identity_missing")
    if now > parse_time(grant.get("expires_at")):
        raise Denied("grant_expired")
    return grant["grant_id"]


def evaluate(manifest, request, grant=None, attestation=None, now=None):
    """Return an admission record, or raise :class:`Denied`.

    Pure and side-effect free so the controller, CI and negative-control tests
    all exercise the identical decision path.
    """
    if not isinstance(request, dict):
        raise Denied("request_invalid")
    now = now or datetime.now(timezone.utc)
    entry = manifest_entry(manifest, request.get("service"))

    uuid = request.get("coolify_uuid")
    if not (isinstance(uuid, str) and COOLIFY_UUID.fullmatch(uuid)):
        raise Denied("invalid_coolify_uuid")
    if uuid != entry.get("coolify_uuid"):
        raise Denied("coolify_uuid_mismatch")
    kind = request.get("coolify_kind")
    if kind not in ("application", "service") or kind != entry.get("coolify_kind"):
        raise Denied("coolify_kind_mismatch")

    pr = request.get("pr")
    if not isinstance(pr, int) or isinstance(pr, bool) or pr < 1:
        raise Denied("invalid_pr")
    source_sha = _require_sha(request.get("source_sha"), "invalid_source_sha")
    merge_sha = _require_sha(request.get("merge_sha"), "invalid_merge_sha")
    # The reviewed tree is squash-merged, so the merged main SHA *is* the
    # source SHA. Any other relationship means an unreviewed tree is deployed.
    if source_sha != merge_sha:
        raise Denied("source_sha_not_merged_source")
    if request.get("base_ref") != RELEASE_BASE_REF:
        raise Denied("unauthorized_release_branch")

    # Hold is a manifest-level gate and is evaluated before any artifact, so a
    # held resource can never be promoted by satisfying later evidence checks.
    state = entry.get("promotion_state", HELD)
    if state not in (HELD, "approved"):
        raise Denied("invalid_promotion_state")
    if state == HELD and not isinstance(grant, dict):
        raise Denied("release_lane_on_hold")

    reviewer, head_sha = _check_review(entry, request)
    digest = _check_attestation(entry, request, attestation, source_sha)
    grant_id = _check_grant(entry, request, grant, source_sha, now)

    return {
        "admit": True,
        "service": entry["id"],
        "coolify_uuid": uuid,
        "coolify_kind": kind,
        "repository": REPO,
        "base_ref": RELEASE_BASE_REF,
        "pr": pr,
        "head_sha": head_sha,
        "source_sha": source_sha,
        "image_digest": digest,
        "reviewer_role": entry.get("reviewer_role"),
        "reviewer_agent_id": reviewer,
        "grant_id": grant_id,
        "attestation_digest": attestation.get("artifact_manifest_digest"),
        "attestation_policy_digest": attestation.get("policy_digest"),
        "test_runner_uid": attestation.get("runner_uid"),
    }


def _load_gate_file(path, label, require_root):
    """Read a JSON gate artifact, refusing symlinks and untrusted ownership."""
    try:
        info = Path(path).lstat()
    except OSError:
        raise Denied(label + "_unavailable") from None
    if not stat.S_ISREG(info.st_mode):
        raise Denied(label + "_not_regular_file")
    if info.st_mode & 0o022:
        raise Denied(label + "_world_writable")
    if require_root and info.st_uid != 0:
        raise Denied(label + "_not_root_owned")
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Denied(label + "_invalid_json") from None
    if not isinstance(data, dict):
        raise Denied(label + "_invalid_shape")
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fail-closed Harness MCP release admission check")
    parser.add_argument("--manifest", default="ops/release-lanes.json")
    parser.add_argument("--request", required=True)
    parser.add_argument("--grant")
    parser.add_argument("--attestation")
    parser.add_argument("--attestation-key")
    parser.add_argument("--now")
    args = parser.parse_args(argv)
    try:
        manifest = _load_gate_file(args.manifest, "manifest", require_root=False)
        request = _load_gate_file(args.request, "request", require_root=True)
        grant = _load_gate_file(args.grant, "grant", require_root=True) if args.grant else None
        attestation = None
        if args.attestation:
            attestation = _load_gate_file(args.attestation, "attestation", require_root=True)
            if not args.attestation_key:
                raise Denied("attestation_key_missing")
            key = Path(args.attestation_key).read_bytes()
            from harness_local_ci_attest import verify_attestation

            if not verify_attestation(attestation, key):
                raise Denied("attestation_signature_invalid")
            attestation["signature_verified"] = True
        now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
        record = evaluate(manifest, request, grant=grant, attestation=attestation, now=now)
        print(json.dumps(record, sort_keys=True))
        return 0
    except Denied as exc:
        print(json.dumps({"admit": False, "reason": str(exc)}), file=sys.stderr)
        return 1
    except OSError:
        print(json.dumps({"admit": False, "reason": "attestation_key_unavailable"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
