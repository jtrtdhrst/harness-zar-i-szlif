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

The promotion path that consumes this decision lives in
:mod:`harness_delivery_controller`: it calls :func:`evaluate` for every service
whose source changed and refuses to build or deploy anything on ``Denied``.
Gate artifacts and key material are read ``O_NOFOLLOW`` and validated with
``fstat`` on the same descriptor that is read, so a path swapped after a check
can never be the bytes that are trusted.
"""
import argparse
import errno
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone

REPO = "jtrtdhrst/harness-zar-i-szlif"
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


class VerifiedAttestation(dict):
    """An attestation whose HMAC was verified in this very process.

    Only :func:`verified_attestation` constructs this type, and it does so after
    :func:`harness_local_ci_attest.verify_attestation` accepted the signature.
    A JSON file - however it is shaped - can never be an instance, so a forged
    ``signature_verified: true`` field, a missing key or a wrong key cannot reach
    admission: trusting a self-asserted flag is the defect this type removes.
    """

    __slots__ = ()


def verified_attestation(attestation, key):
    """Return a :class:`VerifiedAttestation` for ``attestation`` signed by ``key``.

    Verification is performed here and nowhere else, so every caller that wants
    an attestation admitted must present real key material. The signature covers
    every field except ``signature`` itself, which is why splicing a
    ``signature_verified`` flag into an artifact breaks the HMAC instead of
    satisfying the gate.
    """
    from harness_local_ci_attest import verify_attestation

    if not isinstance(attestation, dict) or not isinstance(key, bytes):
        raise Denied("attestation_signature_invalid")
    if not verify_attestation(attestation, key):
        raise Denied("attestation_signature_invalid")
    verified = VerifiedAttestation(attestation)
    verified["signature_verified"] = True
    return verified


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
    if attestation is None:
        raise Denied("local_ci_attestation_missing")
    # Only an attestation verified against real key material in this process is
    # evidence. A raw JSON artifact cannot construct VerifiedAttestation, so a
    # forged `signature_verified: true` is refused before any field is read.
    if not isinstance(attestation, VerifiedAttestation):
        raise Denied("attestation_signature_unverified")
    if attestation.get("schema_version") != ATTESTATION_SCHEMA:
        raise Denied("attestation_schema_invalid")
    # Set by :func:`verified_attestation` after the HMAC check; belt and braces
    # only, because the type check above is what actually proves verification.
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


def _common_request(manifest, request, grant, now, expected_source_sha):
    """Checks shared by build admission and release admission.

    Everything here is required *before* an image exists, so both stages apply
    it identically: service allowlist, Coolify UUID/kind, PR identity, merged
    source SHA, authorized branch, lane hold, independent exact-SHA review and a
    revocable per-UUID grant.

    ``expected_source_sha`` is the exact SHA the caller is about to build or
    deploy (the controller's ``--source-sha``). It is mandatory, so an approved
    request/grant for SHA A can never admit a build of SHA B.
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
    # The SHA being built/deployed must be the SHA the evidence names. Without
    # this binding a request for SHA A would admit any other tree.
    _require_sha(expected_source_sha, "invalid_expected_source_sha")
    if source_sha != expected_source_sha:
        raise Denied("admission_source_sha_mismatch")
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
    if state not in (HELD, "approved", "auto_main"):
        raise Denied("invalid_promotion_state")
    if state == HELD and not isinstance(grant, dict):
        raise Denied("release_lane_on_hold")

    reviewer, head_sha = _check_review(entry, request)
    grant_id = _check_grant(entry, request, grant, source_sha, now)
    return entry, uuid, kind, pr, source_sha, head_sha, reviewer, grant_id


def evaluate_build(manifest, request, grant=None, now=None, *, expected_source_sha):
    """Build-stage admission: may this exact source be built and pushed?

    Identical to :func:`evaluate` except that no root-owned local-CI attestation
    and no immutable digest are required, because neither can exist before the
    image is built. This is *not* permission to deploy: only :func:`evaluate`
    admits a release, and it still demands the attestation, the digest and the
    per-UUID grant for the deploy path.

    ``expected_source_sha`` is keyword-only and has no default, so a caller
    cannot omit the SHA binding by accident: admission of SHA B against SHA A's
    evidence raises ``Denied("admission_source_sha_mismatch")``.
    """
    entry, uuid, kind, pr, source_sha, head_sha, reviewer, grant_id = _common_request(
        manifest, request, grant, now, expected_source_sha)
    return {
        "admit_build": True,
        "service": entry["id"],
        "coolify_uuid": uuid,
        "coolify_kind": kind,
        "repository": REPO,
        "base_ref": RELEASE_BASE_REF,
        "pr": pr,
        "head_sha": head_sha,
        "source_sha": source_sha,
        "reviewer_role": entry.get("reviewer_role"),
        "reviewer_agent_id": reviewer,
        "grant_id": grant_id,
    }


def evaluate(manifest, request, grant=None, attestation=None, now=None, *, expected_source_sha):
    """Return an admission record, or raise :class:`Denied`.

    Pure and side-effect free so the controller, CI and negative-control tests
    all exercise the identical decision path. ``expected_source_sha`` is the
    exact SHA the caller is promoting and is mandatory (keyword-only, no
    default); ``attestation`` must be a :class:`VerifiedAttestation`.
    """
    entry, uuid, kind, pr, source_sha, head_sha, reviewer, grant_id = _common_request(
        manifest, request, grant, now, expected_source_sha)
    digest = _check_attestation(entry, request, attestation, source_sha)

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


def read_trusted_bytes(path, label, require_root=True):
    """Read a trusted gate artifact without a symlink or path-swap window.

    The path is opened ``O_NOFOLLOW`` and every attribute check runs on that
    descriptor's ``fstat``, so replacing the path after the check cannot change
    what is read: there is no separate stat-then-reopen step to race. The
    descriptor is stat'ed again after reading to refuse content that changed
    underneath an open handle.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EMLINK):
            raise Denied(label + "_symlink_refused") from None
        raise Denied(label + "_unavailable") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise Denied(label + "_not_regular_file")
        if info.st_mode & 0o022:
            raise Denied(label + "_world_writable")
        if require_root and info.st_uid != 0:
            raise Denied(label + "_not_root_owned")
        # Root ownership alone does not protect a readable HMAC key or Coolify
        # bearer token. Secret files must be 0600 or stricter, regardless of
        # whether an untrusted user can write them.
        if label in ("attestation_key", "signing_key", "coolify_token") and info.st_mode & 0o077:
            raise Denied(label + "_not_private")
        if info.st_size <= 0 or info.st_size > 262144:
            raise Denied(label + "_invalid_size")
        chunks = []
        try:
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
        except OSError:
            raise Denied(label + "_unreadable") from None
        after = os.fstat(fd)
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise Denied(label + "_changed_during_read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def load_gate_file(path, label, require_root):
    """Read a JSON gate artifact, refusing symlinks and untrusted ownership."""
    raw = read_trusted_bytes(path, label, require_root=require_root)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
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
    parser.add_argument("--source-sha", required=True,
                        help="exact SHA the caller promotes; must match the request")
    parser.add_argument("--now")
    args = parser.parse_args(argv)
    try:
        manifest = load_gate_file(args.manifest, "manifest", require_root=False)
        request = load_gate_file(args.request, "request", require_root=True)
        grant = load_gate_file(args.grant, "grant", require_root=True) if args.grant else None
        attestation = None
        if args.attestation:
            attestation = load_gate_file(args.attestation, "attestation", require_root=True)
            if not args.attestation_key:
                raise Denied("attestation_key_missing")
            # Key material is held to the same descriptor-validated, no-follow
            # rule as the artifacts: an attacker-controlled key path would
            # otherwise verify an attestation the attacker signed. The HMAC is
            # then verified here, and only a VerifiedAttestation is admitted.
            key = read_trusted_bytes(args.attestation_key, "attestation_key", require_root=True)
            attestation = verified_attestation(attestation, key)
        now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
        record = evaluate(manifest, request, grant=grant, attestation=attestation, now=now,
                          expected_source_sha=args.source_sha)
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
