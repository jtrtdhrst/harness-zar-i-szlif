#!/usr/bin/env python3
"""Hold-aware Harness delivery controller (ZARI-240).

This is the reviewed promotion path that consumes
:mod:`harness_release_admission`. The root-owned host unit keeps its own
build/deploy transport (docker build, loopback registry push, Coolify API) and
passes it to :func:`run_promotion`; this module owns *whether* anything may be
promoted, in what order, and what happens when a step fails. It never contacts
a provider itself, so the decision path can be reviewed and tested without host
credentials.

Refusal is total: when admission raises ``Denied`` - held lane, merge without an
independent exact-SHA approval, attestation from another SHA, self-review,
missing/revoked/expired per-UUID grant, changed PR head, unclassifiable changed
path - the controller calls no transport at all, so no image is built, nothing
is deployed and the previously running image stays intact.

Transport contract (duck-typed, supplied by the host unit, never by a PR):

    current(service, coolify_uuid) -> str | None   running immutable digest
    build(service, source_sha) -> str              digest of the built image
    deploy(service, coolify_uuid, coolify_kind, digest) -> str
    health(service, coolify_uuid) -> dict          {"status": "ok", "digest": ...}
    rollback(service, coolify_uuid) -> str

A build whose digest differs from the admitted attestation is never deployed,
and any deploy/health/readback failure triggers exactly one rollback.

``main`` is plan-only: it reports what the controller would do and mutates
nothing, so it can run without a transport and without root.
"""
import argparse
import fcntl
import hashlib
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from harness_release_admission import (DIGEST, SHA, Denied, evaluate, load_gate_file,
                                       read_trusted_bytes, verified_attestation)

STATE_ROOT = "/var/lib/paperclip-gitops"
STATE_FILE = "harness-delivery.json"
LOCK_FILE = "harness-delivery.lock"
MAX_PATHS = 500
KINDS = ("request", "grant", "attestation")


def manifest_services(manifest):
    """Map service id -> manifest entry for every harness-owned resource."""
    if not isinstance(manifest, dict):
        raise Denied("manifest_schema_invalid")
    entries = {}
    for entry in (manifest.get("lanes") or []) + (manifest.get("other_resources") or []):
        if not isinstance(entry, dict):
            raise Denied("manifest_schema_invalid")
        service = entry.get("id")
        if not isinstance(service, str) or not service:
            raise Denied("manifest_schema_invalid")
        if service in entries:
            raise Denied("ambiguous_service")
        entries[service] = entry
    if not entries:
        raise Denied("manifest_schema_invalid")
    return entries


def changed_services(changed_paths, manifest):
    """Attribute changed paths to services; unattributed paths promote nothing."""
    services = manifest_services(manifest)
    if not isinstance(changed_paths, list) or not changed_paths or len(changed_paths) > MAX_PATHS:
        raise Denied("changed_paths_invalid")
    attributed, unclassified = {}, []
    for path in changed_paths:
        if not isinstance(path, str) or not path or path.startswith("/") or "/../" in path:
            raise Denied("changed_paths_invalid")
        owners = [service for service in services if path.startswith(service + "/")]
        if len(owners) > 1:
            raise Denied("ambiguous_changed_path")
        if not owners:
            unclassified.append(path)
            continue
        attributed.setdefault(owners[0], []).append(path)
    return attributed, sorted(unclassified)


def _transport_method(transport, name):
    method = getattr(transport, name, None)
    if not callable(method):
        raise Denied("transport_incomplete")
    return method


def _read_state(state_path):
    if not state_path:
        return {}
    try:
        raw = Path(state_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError:
        raise Denied("controller_state_unreadable") from None
    try:
        data = json.loads(raw)
    except ValueError:
        raise Denied("controller_state_invalid") from None
    if not isinstance(data, dict):
        raise Denied("controller_state_invalid")
    return data


def _write_state(state_path, state):
    if not state_path:
        return
    target = Path(state_path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(tmp), flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def _audit_id(report):
    body = {key: value for key, value in report.items() if key != "audit_id"}
    return "sha256:" + hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _restore(transport, service, uuid, decision, reason):
    """Attempt exactly one rollback; a failed restore must never escape.

    Every failure path goes through here so the controller always returns an
    auditable report: the rollback attempt is recorded, and a rollback that
    raises becomes ``rollback_failed`` with the error class instead of an
    exception that loses the audit id and the promotion state.
    """
    try:
        rollback = transport.rollback(service, uuid)
    except Exception as inner:
        decision.update(decision="rollback_failed", reason=reason,
                        rollback_error=type(inner).__name__)
        return decision
    decision.update(decision="rolled_back", reason=reason, rollback=rollback)
    return decision


def _promote(service, record, transport, state, state_path):
    """Build -> verify digest -> deploy -> verify health; one rollback on failure."""
    uuid = record["coolify_uuid"]
    kind = record["coolify_kind"]
    admitted = record["image_digest"]
    decision = {"service": service, "coolify_uuid": uuid, "source_sha": record["source_sha"],
                "image_digest": admitted}
    try:
        previous = transport.current(service, uuid)
    except Exception as exc:  # nothing has been mutated yet: report and stop
        decision.update(decision="denied", reason="transport_failed:" + type(exc).__name__)
        return decision
    decision["previous_image_digest"] = previous
    if isinstance(previous, str) and previous == admitted and state.get(service, {}).get("source_sha") == record["source_sha"]:
        # Idempotence is not a substitute for live acceptance. The image may
        # still be pinned while the container is unhealthy, stopped or running
        # another revision. No rebuild/deploy is needed, but the readback must
        # prove both image digest and exact source SHA before returning success.
        try:
            health = transport.health(service, uuid)
        except Exception:
            decision.update(decision="denied", reason="already_delivered_health_unavailable")
            return decision
        if not isinstance(health, dict) or health.get("status") != "ok":
            decision.update(decision="denied", reason="already_delivered_unhealthy")
            return decision
        if health.get("digest") != admitted or health.get("source_sha") != record["source_sha"]:
            decision.update(decision="denied", reason="already_delivered_revision_mismatch")
            return decision
        decision.update(decision="already_delivered", health=health)
        return decision
    try:
        built = transport.build(service, record["source_sha"])
    except Exception as exc:  # a failed build leaves the running image untouched
        decision.update(decision="denied", reason="transport_failed:" + type(exc).__name__)
        return decision
    # A digest that differs from the attested artifact is not the reviewed
    # image; it is never deployed and nothing needs rolling back.
    if not isinstance(built, str) or not DIGEST.fullmatch(built):
        decision.update(decision="denied", reason="build_digest_invalid")
        return decision
    decision["built_image_digest"] = built
    if built != admitted:
        decision.update(decision="denied", reason="build_digest_mismatch")
        return decision
    try:
        deployment = transport.deploy(service, uuid, kind, built)
        decision["deployment"] = deployment
        health = transport.health(service, uuid)
        if not isinstance(health, dict) or health.get("status") != "ok" or health.get("digest") != admitted:
            raise Denied("post_deploy_health_failed")
        # The deployed service must report the exact source SHA it runs. Absent
        # evidence is not evidence: a health payload without it is refused, so
        # a readback that cannot prove provenance never counts as promotion.
        reported_sha = health.get("source_sha")
        if reported_sha is None:
            raise Denied("post_deploy_source_sha_missing")
        if reported_sha != record["source_sha"]:
            raise Denied("post_deploy_source_sha_mismatch")
    except Denied as exc:
        return _restore(transport, service, uuid, decision, str(exc))
    except Exception as exc:  # transport/proxy failure: restore, never leave a half release
        return _restore(transport, service, uuid, decision, "transport_failed:" + type(exc).__name__)
    decision.update(decision="promoted", health=health)
    state[service] = {"coolify_uuid": uuid, "source_sha": record["source_sha"],
                      "image_digest": admitted, "deployment": deployment,
                      "promoted_at": datetime.now(timezone.utc).isoformat()}
    try:
        _write_state(state_path, state)
    except OSError:
        # An unrecordable promotion is not a completed promotion: restore the
        # previous image rather than leave an unrecorded release running.
        state.pop(service, None)
        return _restore(transport, service, uuid, decision, "promotion_state_unwritable")
    return decision


def run_promotion(manifest, changed_paths, artifacts, transport, now=None,
                  state_path=None, lock_path=None, *, source_sha, pre_admitted=None):
    """Return an audit report; mutate nothing unless every gate admits.

    ``artifacts(service)`` returns ``{"request": ..., "grant": ..., "attestation": ...}``
    loaded from root-owned files. ``transport`` is the host unit's build/deploy
    adapter. ``source_sha`` is the exact SHA this promotion is for and is
    mandatory: every service's request and grant must name it, so admission of
    one SHA can never build or deploy another. A held or unapproved change
    yields a report with ``promoted: False`` and no transport call whatsoever.
    """
    if not isinstance(source_sha, str) or not SHA.fullmatch(source_sha):
        raise Denied("invalid_source_sha")
    attributed, unclassified = {}, []
    report = {"source_sha": source_sha, "unclassified_paths": unclassified, "decisions": [],
              "promoted": False, "mutated": False}
    lock_handle = None
    try:
        attributed, unclassified = changed_services(changed_paths, manifest)
        report["unclassified_paths"] = unclassified
        if not attributed:
            report["result"] = "no_service_change"
            report["audit_id"] = _audit_id(report)
            return report
        if lock_path:
            Path(lock_path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            lock_handle = open(lock_path, "a+", encoding="utf-8")
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise Denied("controller_locked") from None
        state = _read_state(state_path)
        for service in sorted(attributed):
            decision = {"service": service, "changed_paths": sorted(attributed[service])}
            try:
                if pre_admitted is not None and service in pre_admitted:
                    # Trusted-main auto lane: the caller already verified exact
                    # source/digest and the manifest authorizes automatic
                    # promotion. No per-release request/grant artifact exists.
                    record = pre_admitted[service]
                    if (not isinstance(record, dict)
                            or record.get("service") != service
                            or record.get("source_sha") != source_sha
                            or not isinstance(record.get("image_digest"), str)
                            or not DIGEST.fullmatch(record["image_digest"])):
                        raise Denied("auto_admission_invalid")
                else:
                    bundle = artifacts(service)
                    if not isinstance(bundle, dict):
                        raise Denied("gate_artifacts_invalid")
                    request = bundle.get("request")
                    record = evaluate(manifest, request, grant=bundle.get("grant"),
                                      attestation=bundle.get("attestation"), now=now,
                                      expected_source_sha=source_sha)
            except Denied as exc:
                decision.update(decision="denied", reason=str(exc))
                report["decisions"].append(decision)
                continue
            if transport is None:
                decision.update(decision="admissible_no_transport",
                                image_digest=record["image_digest"],
                                coolify_uuid=record["coolify_uuid"])
                report["decisions"].append(decision)
                continue
            for name in ("current", "build", "deploy", "health", "rollback"):
                _transport_method(transport, name)
            outcome = _promote(service, record, transport, state, state_path)
            report["decisions"].append(decision | outcome)
            if outcome.get("decision") == "promoted":
                report["promoted"] = True
                report["mutated"] = True
            elif outcome.get("decision") in ("rolled_back", "rollback_failed"):
                report["mutated"] = True
    except Denied as exc:
        report["result"] = "denied"
        report["reason"] = str(exc)
    finally:
        if lock_handle is not None:
            lock_handle.close()
    report.setdefault("result", "promoted" if report["promoted"] else "held")
    report["audit_id"] = _audit_id(report)
    return report


def git_changed_paths(repo, base_sha, source_sha):
    """Exact changed paths between two commits, fail-closed on ambiguity."""
    for sha in (base_sha, source_sha):
        if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
            raise Denied("invalid_source_sha")
    try:
        completed = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", base_sha, source_sha],
                                   capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        raise Denied("git_unavailable") from None
    if completed.returncode != 0:
        raise Denied("git_diff_failed")
    paths = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not paths or len(paths) > MAX_PATHS:
        raise Denied("changed_paths_unbounded")
    return paths


def load_artifacts(artifact_dir, service, attestation_key, *, allow_missing_attestation=False):
    """Load the three gate artifacts for one service from root-owned files.

    An attestation is only evidence after its HMAC was verified with real key
    material, so ``attestation_key`` is mandatory whenever an attestation file is
    present: there is no code path that returns a raw JSON attestation for
    admission. ``allow_missing_attestation`` is used by the prepare stage, where
    nothing is deployed, and simply returns ``None`` so the release evaluation
    denies with ``local_ci_attestation_missing``.
    """
    base = Path(artifact_dir)
    bundle = {}
    for kind in KINDS:
        path = base / (service + "-" + kind + ".json")
        try:
            bundle[kind] = load_gate_file(path, kind, require_root=True)
        except Denied as exc:
            if kind == "grant" and str(exc) == "grant_unavailable":
                bundle[kind] = None
                continue
            if kind == "attestation" and allow_missing_attestation:
                bundle[kind] = None
                continue
            raise
    if bundle.get("attestation") is None:
        return bundle
    if not attestation_key:
        raise Denied("attestation_key_missing")
    key = read_trusted_bytes(attestation_key, "attestation_key", require_root=True)
    bundle["attestation"] = verified_attestation(bundle["attestation"], key)
    return bundle


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hold-aware Harness delivery controller (plan only)")
    parser.add_argument("--manifest", default="ops/release-lanes.json")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--attestation-key")
    parser.add_argument("--now")
    args = parser.parse_args(argv)
    try:
        manifest = load_gate_file(args.manifest, "manifest", require_root=False)
        paths = git_changed_paths(args.repo, args.base_sha, args.source_sha)
        artifacts = lambda service: load_artifacts(args.artifact_dir, service, args.attestation_key)
        now = None
        if args.now:
            from harness_release_admission import parse_time

            now = parse_time(args.now)
        report = run_promotion(manifest, paths, artifacts, transport=None, now=now,
                               source_sha=args.source_sha)
        print(json.dumps(report, sort_keys=True))
        return 0
    except Denied as exc:
        print(json.dumps({"result": "denied", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
