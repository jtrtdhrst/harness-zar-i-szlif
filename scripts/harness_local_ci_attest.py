#!/usr/bin/env python3
"""Root-invoked Harness local-CI attester (ZARI-240).

Produces the provenance artifact that :mod:`harness_release_admission` consumes:
it runs the declared per-service test commands at one exact source SHA on the
approved host, records every command with its exit code, the changed-path
artifact manifest and the immutable image digest, then writes an HMAC-signed
attestation into a root-only directory.

Properties required by the release contract:

* no network credential and no GitHub Actions billing dependency;
* single-writer serialization through an exclusive lock;
* idempotent for an identical ``(service, source_sha, image_digest, commands)``
  tuple, so a retried timer tick cannot rewrite history;
* fail-closed on stale SHA, failing tests, empty evidence or untrusted output;
* never pushes, merges, deploys or mutates a provider.

``main`` requires uid 0. The installed host copy and its systemd unit are a
separate, explicitly audited owner activation; this file is source only.
"""
import argparse
import fcntl
import hashlib
import hmac
import json
import os
import socket
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
SHA_HEX = 40
DEFAULT_OUT = Path("/var/lib/paperclip-gitops/harness-attestations")
DEFAULT_KEY = Path("/etc/paperclip-gitops/harness-attestation.key")
TEST_TIMEOUT = 1800


class Denied(Exception):
    """Attestation cannot be produced. The message is a stable reason code."""


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def signed_payload(attestation):
    return {key: value for key, value in attestation.items() if key != "signature"}


def sign(attestation, key):
    if not isinstance(key, bytes) or len(key) < 32:
        raise Denied("signing_key_weak")
    return hmac.new(key, canonical(signed_payload(attestation)), hashlib.sha256).hexdigest()


def verify_attestation(attestation, key):
    """Constant-time structural + HMAC verification. Never trusts self-report."""
    if not isinstance(attestation, dict) or not isinstance(key, bytes):
        return False
    signature = attestation.get("signature")
    if not isinstance(signature, str) or len(signature) != 64:
        return False
    if attestation.get("schema_version") != SCHEMA:
        return False
    try:
        expected = sign(attestation, key)
    except Denied:
        return False
    return hmac.compare_digest(expected, signature)


def validate_results(results):
    """Reject empty, malformed or duplicated test evidence; require all passing."""
    if not isinstance(results, list) or not results:
        raise Denied("attestation_tests_missing")
    seen = set()
    cleaned = []
    for record in results:
        if not isinstance(record, dict):
            raise Denied("attestation_test_record_invalid")
        command = record.get("command")
        exit_code = record.get("exit")
        if not isinstance(command, str) or not command.strip() or len(command) > 500:
            raise Denied("attestation_test_record_invalid")
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            raise Denied("attestation_test_record_invalid")
        if command in seen:
            raise Denied("attestation_test_duplicate")
        seen.add(command)
        if exit_code != 0:
            raise Denied("attestation_tests_failed")
        cleaned.append({"command": command, "exit": exit_code})
    return cleaned


def validate_identity(service, source_sha, changed_paths, image_digest):
    if not isinstance(service, str) or not service or "/" in service or len(service) > 64:
        raise Denied("invalid_service_id")
    if not isinstance(source_sha, str) or len(source_sha) != SHA_HEX or any(c not in "0123456789abcdef" for c in source_sha):
        raise Denied("invalid_source_sha")
    if not isinstance(image_digest, str) or not image_digest.startswith("sha256:") or len(image_digest) != 71:
        raise Denied("invalid_image_digest")
    if not isinstance(changed_paths, list) or not changed_paths:
        raise Denied("changed_paths_missing")
    prefix = service + "/"
    for path in changed_paths:
        if not isinstance(path, str) or not path.startswith(prefix) or path.startswith("/") or "/../" in path:
            raise Denied("changed_paths_outside_service")
    return sorted(set(changed_paths))


def manifest_digest(changed_paths, image_digest, source_sha):
    """Stable digest over the artifact manifest, independent of test timing."""
    body = {"changed_paths": sorted(set(changed_paths)), "image_digest": image_digest, "source_sha": source_sha}
    return "sha256:" + hashlib.sha256(canonical(body)).hexdigest()


def build_attestation(service, source_sha, results, changed_paths, image_digest, key,
                      host="localhost", created_at=None, attestor_uid=0):
    """Assemble and sign an attestation. Raises Denied on any invalid input."""
    cleaned = validate_results(results)
    paths = validate_identity(service, source_sha, changed_paths, image_digest)
    attestation = {
        "schema_version": SCHEMA,
        "service": service,
        "source_sha": source_sha,
        "image_digest": image_digest,
        "tests": cleaned,
        "changed_paths": paths,
        "artifact_manifest_digest": manifest_digest(paths, image_digest, source_sha),
        "attestor_uid": attestor_uid,
        "attestor_host": host,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    attestation["signature"] = sign(attestation, key)
    return attestation


def reusable(existing, service, source_sha, image_digest, commands, key):
    """True only for a fully valid attestation of the identical run identity."""
    if not isinstance(existing, dict) or not verify_attestation(existing, key):
        return False
    if (existing.get("service"), existing.get("source_sha"), existing.get("image_digest")) != (service, source_sha, image_digest):
        return False
    recorded = [item.get("command") for item in existing.get("tests") or [] if isinstance(item, dict)]
    return recorded == list(commands)


def attestation_path(out_dir, service, source_sha):
    return Path(out_dir) / (service + "-" + source_sha + ".json")


def command_string(argv):
    if not isinstance(argv, (list, tuple)) or not argv or any(not isinstance(a, str) or not a for a in argv):
        raise Denied("invalid_test_command")
    return " ".join(argv)


def run_tests(commands, cwd, timeout=TEST_TIMEOUT):
    """Run each argv list without a shell; record exit codes, not stdout."""
    results = []
    for argv in commands:
        label = command_string(argv)
        started = time.monotonic()
        try:
            completed = subprocess.run(argv, cwd=str(cwd), timeout=timeout,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            raise Denied("test_command_unavailable") from None
        results.append({"command": label, "exit": completed.returncode,
                        "seconds": round(time.monotonic() - started, 3)})
    return results


def changed_paths(repo, base_sha, source_sha):
    """Exact changed paths of the reviewed tree, fail-closed on ambiguity."""
    if not isinstance(base_sha, str) or len(base_sha) != SHA_HEX or len(source_sha) != SHA_HEX:
        raise Denied("invalid_base_sha")
    try:
        completed = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", base_sha, source_sha],
                                   capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        raise Denied("git_unavailable") from None
    if completed.returncode != 0:
        raise Denied("git_diff_failed")
    paths = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not paths or len(paths) > 500:
        raise Denied("changed_paths_unbounded")
    return paths


def _read_key(path, require_root):
    try:
        info = Path(path).lstat()
    except OSError:
        raise Denied("signing_key_unavailable") from None
    if not stat.S_ISREG(info.st_mode):
        raise Denied("signing_key_not_regular_file")
    if info.st_mode & 0o077:
        raise Denied("signing_key_permissions_too_open")
    if require_root and info.st_uid != 0:
        raise Denied("signing_key_not_root_owned")
    key = Path(path).read_bytes()
    if len(key) < 32:
        raise Denied("signing_key_weak")
    return key


def write_atomic(path, payload):
    tmp = path.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Root-invoked Harness local CI attester")
    parser.add_argument("--service", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--test-command", action="append", default=[],
                        help="Repeatable; one argv list per occurrence (JSON array)")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--key-file", default=str(DEFAULT_KEY))
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; write nothing")
    args = parser.parse_args(argv)
    if os.geteuid() != 0 and not args.dry_run:
        raise SystemExit("requires root on the approved host (or --dry-run)")
    try:
        commands = [json.loads(item) for item in args.test_command]
        for argv_list in commands:
            command_string(argv_list)
        key = _read_key(args.key_file, require_root=os.geteuid() == 0)
        paths = changed_paths(args.repo, args.base_sha, args.source_sha)
        validate_identity(args.service, args.source_sha, paths, args.image_digest)
        target = attestation_path(args.out_dir, args.service, args.source_sha)
        if args.dry_run:
            print(json.dumps({"result": "plan", "service": args.service, "source_sha": args.source_sha,
                              "changed_paths": paths, "commands": [command_string(c) for c in commands],
                              "target": str(target)}, sort_keys=True))
            return 0
        Path(args.out_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(Path(args.out_dir) / (args.service + ".lock"), "a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            if target.exists():
                existing = json.loads(target.read_text(encoding="utf-8"))
                if reusable(existing, args.service, args.source_sha, args.image_digest,
                            [command_string(c) for c in commands], key):
                    print(json.dumps({"result": "reused", "attestation": str(target)}, sort_keys=True))
                    return 0
            results = run_tests(commands, args.repo)
            attestation = build_attestation(args.service, args.source_sha, results, paths,
                                            args.image_digest, key, host=socket.gethostname())
            write_atomic(target, attestation)
        print(json.dumps({"result": "attested", "attestation": str(target),
                          "artifact_manifest_digest": attestation["artifact_manifest_digest"]}, sort_keys=True))
        return 0
    except Denied as exc:
        print(json.dumps({"result": "denied", "reason": str(exc)}), file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print(json.dumps({"result": "denied", "reason": "attestation_io_failed"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
