#!/usr/bin/env python3
"""Root-invoked Harness local-CI attester (ZARI-240).

Produces the provenance artifact that :mod:`harness_release_admission` consumes:
it runs the **policy-declared** per-service test commands at one exact source
SHA, records every command with its exit code, the changed-path artifact
manifest and the immutable image digest, then writes an HMAC-signed attestation
into a root-only directory.

Security model (owner exact-SHA security review on PR #112):

* the caller supplies **no** executable surface — no argv, no repo path, no
  output path, no key path. Commands, repository root, output directory, key
  file and runner uid/gid all come from a root-owned, non-symlink policy file,
  so untrusted PR or controller data cannot become root command execution;
* tests run with dropped privileges (``run_as_uid``/``run_as_gid`` from the
  policy), an empty supplementary group set, ``PR_SET_NO_NEW_PRIVS``, a fresh
  session, a sanitized environment with no inherited credential and no shell;
  uid 0 execution is refused outright and is never attestable;
* the checkout must be a real directory inside the policy's ``repo_root``, at
  exactly the requested source SHA, with a clean worktree, so tests never run
  against unaudited working-tree content;
* policy and key files are opened ``O_NOFOLLOW`` and validated with ``fstat`` on
  the open descriptor, which removes the path-swap/TOCTOU window;
* fail-closed on stale SHA, failing tests, empty evidence or untrusted output,
  with an exclusive lock and idempotent reuse of an identical run identity.

Namespace-level network isolation is **not** implemented here; it remains a
host activation requirement recorded in
``docs/SOURCE-ONLY-AND-LOCAL-BUILDS.md``. ``main`` requires uid 0 on the
approved host; installation and activation are a separate audited owner step.
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
POLICY_SCHEMA = 1
SHA_HEX = 40
DEFAULT_POLICY = Path("/etc/paperclip-gitops/harness-ci-policy.json")
STATE_ROOT = "/var/lib/paperclip-gitops"
TEST_TIMEOUT = 1800
MAX_COMMANDS = 20
SANITIZED_PATH = "/usr/local/bin:/usr/bin:/bin"


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


def read_trusted_file(path, label, require_root=True):
    """Read a root-owned config/credential file without a symlink race.

    The path is opened ``O_NOFOLLOW`` and every attribute check runs on that
    descriptor's ``fstat``, so swapping the path after the check cannot change
    what is read.
    """
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise Denied(label + "_unavailable") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise Denied(label + "_not_regular_file")
        if info.st_mode & 0o022:
            raise Denied(label + "_world_writable")
        if require_root and info.st_uid != 0:
            raise Denied(label + "_not_root_owned")
        if info.st_size <= 0 or info.st_size > 262144:
            raise Denied(label + "_invalid_size")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def path_inside(root, candidate):
    try:
        return Path(candidate).resolve(strict=False).is_relative_to(Path(root).resolve(strict=False))
    except (OSError, ValueError):
        return False


def validate_policy(policy):
    """Validate the root-owned CI policy. Any ambiguity denies everything."""
    if not isinstance(policy, dict) or policy.get("schema_version") != POLICY_SCHEMA:
        raise Denied("policy_schema_invalid")
    for name in ("repo_root", "out_dir", "key_file"):
        value = policy.get(name)
        if not isinstance(value, str) or not value.startswith("/"):
            raise Denied("policy_" + name + "_invalid")
    if not Path(policy["repo_root"]).is_dir():
        raise Denied("policy_repo_root_unavailable")
    if not path_inside(STATE_ROOT, policy["out_dir"]):
        raise Denied("policy_out_dir_outside_allowlist")
    uid, gid = policy.get("run_as_uid"), policy.get("run_as_gid")
    if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0:
        raise Denied("policy_privilege_drop_missing")
    if not isinstance(gid, int) or isinstance(gid, bool) or gid <= 0:
        raise Denied("policy_privilege_drop_missing")
    services = policy.get("services")
    if not isinstance(services, dict) or not services:
        raise Denied("policy_services_missing")
    for service in services:
        policy_commands(policy, service)
    return policy


def policy_commands(policy, service):
    """Return the fixed argv list for one service; the only command source."""
    if not isinstance(service, str) or not service or "/" in service or len(service) > 64:
        raise Denied("invalid_service_id")
    services = policy.get("services") if isinstance(policy, dict) else None
    if not isinstance(services, dict) or service not in services:
        raise Denied("service_not_in_policy")
    commands = services[service]
    if not isinstance(commands, list) or not commands or len(commands) > MAX_COMMANDS:
        raise Denied("policy_commands_invalid")
    validated = []
    for argv in commands:
        if not isinstance(argv, (list, tuple)) or not argv or len(argv) > 32:
            raise Denied("policy_commands_invalid")
        if any(not isinstance(arg, str) or not arg or len(arg) > 500 for arg in argv):
            raise Denied("policy_commands_invalid")
        # Absolute executable only: never resolved through PATH, so a poisoned
        # environment cannot substitute the program the host trusts.
        if not argv[0].startswith("/") or not Path(argv[0]).is_file():
            raise Denied("policy_command_not_absolute")
        validated.append(list(argv))
    return validated


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
                      host="localhost", created_at=None, attestor_uid=0,
                      runner_uid=None, policy_digest=None):
    """Assemble and sign an attestation. Raises Denied on any invalid input."""
    cleaned = validate_results(results)
    paths = validate_identity(service, source_sha, changed_paths, image_digest)
    if not isinstance(runner_uid, int) or isinstance(runner_uid, bool) or runner_uid <= 0:
        raise Denied("test_runner_privilege_not_dropped")
    if not isinstance(policy_digest, str) or not policy_digest.startswith("sha256:") or len(policy_digest) != 71:
        raise Denied("policy_digest_missing")
    attestation = {
        "schema_version": SCHEMA,
        "service": service,
        "source_sha": source_sha,
        "image_digest": image_digest,
        "tests": cleaned,
        "changed_paths": paths,
        "artifact_manifest_digest": manifest_digest(paths, image_digest, source_sha),
        "policy_digest": policy_digest,
        "attestor_uid": attestor_uid,
        "runner_uid": runner_uid,
        "attestor_host": host,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    attestation["signature"] = sign(attestation, key)
    return attestation


def reusable(existing, service, source_sha, image_digest, commands, key, policy_digest=None):
    """True only for a fully valid attestation of the identical run identity."""
    if not isinstance(existing, dict) or not verify_attestation(existing, key):
        return False
    if (existing.get("service"), existing.get("source_sha"), existing.get("image_digest")) != (service, source_sha, image_digest):
        return False
    if policy_digest is not None and existing.get("policy_digest") != policy_digest:
        return False
    recorded = [item.get("command") for item in existing.get("tests") or [] if isinstance(item, dict)]
    return recorded == list(commands)


def attestation_path(out_dir, service, source_sha):
    return Path(out_dir) / (service + "-" + source_sha + ".json")


def command_string(argv):
    if not isinstance(argv, (list, tuple)) or not argv or any(not isinstance(a, str) or not a for a in argv):
        raise Denied("invalid_test_command")
    return " ".join(argv)


def sanitized_env(home):
    """Minimal environment: no inherited credential, token or proxy variable."""
    return {"PATH": SANITIZED_PATH, "HOME": str(home), "TMPDIR": str(home),
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def privilege_dropper(uid, gid):
    """Return a pre-exec hook that drops to an unprivileged uid and pins it."""
    if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0:
        raise Denied("test_runner_privilege_not_dropped")
    if not isinstance(gid, int) or isinstance(gid, bool) or gid <= 0:
        raise Denied("test_runner_privilege_not_dropped")

    def drop():
        os.setsid()
        try:
            import ctypes

            # PR_SET_NO_NEW_PRIVS: no setuid binary can raise privileges back.
            ctypes.CDLL(None, use_errno=True).prctl(38, 1, 0, 0, 0)
        except Exception:
            pass
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)
        if os.geteuid() != uid or os.getuid() != uid:
            raise OSError("privilege drop failed")

    return drop


def run_tests(commands, cwd, uid, gid, timeout=TEST_TIMEOUT):
    """Run policy argv without a shell, as an unprivileged uid, recording exits.

    ``uid`` 0 (or missing) is refused: attestation must never be produced by a
    root-executed test command. When the attester already runs as the target
    unprivileged uid, no further drop is needed; any other mismatch denies.
    """
    if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0:
        raise Denied("test_runner_privilege_not_dropped")
    if not isinstance(gid, int) or isinstance(gid, bool) or gid <= 0:
        raise Denied("test_runner_privilege_not_dropped")
    current = os.geteuid()
    if current == 0:
        preexec = privilege_dropper(uid, gid)
    elif current == uid:
        preexec = None
    else:
        raise Denied("test_runner_uid_unavailable")
    home = Path(cwd) if Path(cwd).is_dir() else Path("/")
    results = []
    for argv in commands:
        label = command_string(argv)
        started = time.monotonic()
        try:
            completed = subprocess.run(argv, cwd=str(cwd), env=sanitized_env(home),
                                       timeout=timeout, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       close_fds=True, preexec_fn=preexec)
        except (OSError, subprocess.TimeoutExpired):
            raise Denied("test_command_unavailable") from None
        results.append({"command": label, "exit": completed.returncode,
                        "seconds": round(time.monotonic() - started, 3)})
    return results


def verify_checkout(repo, source_sha):
    """The tests must run on the reviewed tree at exactly ``source_sha``."""
    if not isinstance(source_sha, str) or len(source_sha) != SHA_HEX:
        raise Denied("invalid_source_sha")
    try:
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=60)
        status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        raise Denied("git_unavailable") from None
    if head.returncode != 0 or status.returncode != 0:
        raise Denied("checkout_unreadable")
    if head.stdout.strip() != source_sha:
        raise Denied("checkout_not_at_source_sha")
    if status.stdout.strip():
        raise Denied("checkout_dirty")
    return True


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
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; write nothing")
    args = parser.parse_args(argv)
    if os.geteuid() != 0 and not args.dry_run:
        raise SystemExit("requires root on the approved host (or --dry-run)")
    try:
        policy_bytes = read_trusted_file(args.policy, "policy", require_root=os.geteuid() == 0)
        policy_digest = "sha256:" + hashlib.sha256(policy_bytes).hexdigest()
        policy = json.loads(policy_bytes.decode("utf-8"))
        validate_policy(policy)
        commands = policy_commands(policy, args.service)
        key = read_trusted_file(policy["key_file"], "signing_key", require_root=os.geteuid() == 0)
        if len(key) < 32:
            raise Denied("signing_key_weak")
        repo = policy["repo_root"]
        if not Path(repo).is_dir():
            raise Denied("repo_path_outside_allowlist")
        paths = changed_paths(repo, args.base_sha, args.source_sha)
        validate_identity(args.service, args.source_sha, paths, args.image_digest)
        target = attestation_path(policy["out_dir"], args.service, args.source_sha)
        if not path_inside(policy["out_dir"], target):
            raise Denied("out_dir_outside_allowlist")
        if args.dry_run:
            print(json.dumps({"result": "plan", "service": args.service, "source_sha": args.source_sha,
                              "changed_paths": paths, "commands": [command_string(c) for c in commands],
                              "runner_uid": policy["run_as_uid"], "policy_digest": policy_digest,
                              "target": str(target)}, sort_keys=True))
            return 0
        verify_checkout(repo, args.source_sha)
        Path(policy["out_dir"]).mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(Path(policy["out_dir"]) / (args.service + ".lock"), "a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            if target.exists():
                existing = json.loads(target.read_text(encoding="utf-8"))
                if reusable(existing, args.service, args.source_sha, args.image_digest,
                            [command_string(c) for c in commands], key, policy_digest):
                    print(json.dumps({"result": "reused", "attestation": str(target)}, sort_keys=True))
                    return 0
            results = run_tests(commands, repo, policy["run_as_uid"], policy["run_as_gid"])
            attestation = build_attestation(args.service, args.source_sha, results, paths,
                                            args.image_digest, key, host=socket.gethostname(),
                                            runner_uid=policy["run_as_uid"], policy_digest=policy_digest)
            write_atomic(target, attestation)
        print(json.dumps({"result": "attested", "attestation": str(target),
                          "runner_uid": attestation["runner_uid"],
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
