#!/usr/bin/env python3
"""Root-install preflight and runbook generator for the Harness delivery gate.

Operator tool, not an installer. It never writes a host file, never stops or
starts a unit and never reads a secret: it verifies the preconditions an
authorized root operator must satisfy before installing the reviewed controller,
and it prints the exact ordered command plan (with the immutable expected
hashes) so the installation is a reviewed, reproducible act rather than an
improvised one.

Read-only by design:

* ``--check`` (default) reports ``ready`` plus every blocker.
* ``--plan`` additionally prints the ordered install/stage/verify/canary/rollback
  command list. It refuses to emit a plan while the delivery timer is active,
  while the approved module hashes do not match the exact approved SHA, or while
  the installed files are not root-owned.

The install itself, the timer stop and the negative canaries on the live host are
OPERATOR_ONLY steps documented in ``ops/harness/INSTALL-RUNBOOK.md``.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

LIBEXEC = Path("/usr/local/libexec")
ETC = Path("/etc/paperclip-gitops")
STATE = Path("/var/lib/harness-image-delivery")
POLICY = ETC / "harness-ci-policy.json"
KEY = ETC / "harness-attestation.key"
TIMER = "harness-image-delivery.timer"
SERVICE = "harness-image-delivery.service"
MODULES = ("harness_release_admission.py", "harness_local_ci_attest.py",
           "harness_delivery_controller.py", "harness_native_delivery.py")


class Probe:
    """Every host read the preflight performs, so tests can supply a fake."""

    def is_active(self, unit):
        completed = subprocess.run(["systemctl", "is-active", unit],
                                   capture_output=True, text=True, timeout=30)
        return completed.stdout.strip() == "active"

    def stat(self, path):
        """Return {'uid','mode','exists'} for a path."""
        try:
            info = os.lstat(path)
        except OSError:
            return {"exists": False, "uid": None, "mode": None}
        return {"exists": True, "uid": info.st_uid, "mode": info.st_mode & 0o777}

    def sha256(self, path):
        import hashlib

        try:
            return hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except OSError:
            return None

    def euid(self):
        return os.geteuid()


def blob_sha256(repo, sha, path):
    """sha256 of one file as committed at an exact SHA (no checkout needed)."""
    completed = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{path}"],
                               capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(f"cannot read {path} at {sha}")
    import hashlib

    return hashlib.sha256(completed.stdout).hexdigest()


def expected_hashes(repo, sha, modules=MODULES):
    """Immutable expected digests for the modules approved at ``sha``."""
    return {name: blob_sha256(repo, sha, f"scripts/{name}") for name in modules}


def check(probe, repo, sha):
    """Return (checks, blockers). Read-only; never mutates anything."""
    checks, blockers = {}, []

    def record(name, ok, detail):
        checks[name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            blockers.append(name)

    record("operator_root", probe.euid() == 0,
           "installation requires uid 0; this session is uid %s" % probe.euid())
    record("timer_inactive", not probe.is_active(TIMER),
           "delivery timer must be stopped before any install step")
    record("service_inactive", not probe.is_active(SERVICE),
           "delivery oneshot service must not be running")

    try:
        expected = expected_hashes(repo, sha)
        record("approved_sha_present", True, sha)
    except RuntimeError as exc:
        expected = {}
        record("approved_sha_present", False, str(exc))

    installed = {}
    for name in MODULES:
        path = LIBEXEC / name
        info = probe.stat(path)
        digest = probe.sha256(path) if info["exists"] else None
        installed[name] = {"exists": info["exists"], "uid": info["uid"],
                           "mode": info["mode"], "sha256": digest}
        if info["exists"]:
            record(f"{name}_root_owned", info["uid"] == 0,
                   f"uid={info['uid']} mode={oct(info['mode'] or 0)}")
            record(f"{name}_matches_approved_sha", digest == expected.get(name),
                   "installed=%s expected=%s" % (digest, expected.get(name)))

    legacy = LIBEXEC / "harness_image_delivery.py"
    info = probe.stat(legacy)
    record("legacy_controller_present_to_back_up", info["exists"],
           "the hold-blind controller must be backed up before replacement")

    policy = probe.stat(POLICY)
    record("policy_present", policy["exists"], str(POLICY))
    if policy["exists"]:
        record("policy_root_private", policy["uid"] == 0 and policy["mode"] == 0o600,
               f"uid={policy['uid']} mode={oct(policy['mode'] or 0)}")
    key = probe.stat(KEY)
    record("attestation_key_present", key["exists"], str(KEY))
    if key["exists"]:
        record("attestation_key_root_private", key["uid"] == 0 and key["mode"] == 0o600,
               f"uid={key['uid']} mode={oct(key['mode'] or 0)}")
    record("state_dir_present", probe.stat(STATE)["exists"], str(STATE))
    return checks, blockers, installed, expected


def install_plan(sha, expected):
    """Ordered operator steps; each tuple is (step, command(s), precondition)."""
    backup = STATE / "backups" / f"harness_image_delivery-{sha[:12]}.py"
    steps = [
        ("01_stop_timer",
         ["systemctl stop harness-image-delivery.timer", "systemctl stop harness-image-delivery.service"],
         "timer and oneshot service inactive; delivery lock unheld"),
        ("02_backup_legacy_controller",
         [f"install -o root -g root -m 0600 {LIBEXEC / 'harness_image_delivery.py'} {backup}",
          f"sha256sum {LIBEXEC / 'harness_image_delivery.py'} {backup}"],
         "legacy_controller_present_to_back_up"),
        ("03_stage_modules",
         [f"git -C <repo> show {sha}:scripts/{name} | install -o root -g root -m 0644 /dev/stdin {LIBEXEC / name}"
          for name in MODULES],
         "approved_sha_present"),
        ("04_verify_staged_hashes",
         [f"test \"$(sha256sum {LIBEXEC / name} | cut -d' ' -f1)\" = {expected[name]}" for name in MODULES],
         "every installed module matches the approved SHA digest"),
        ("05_install_policy_and_key",
         [f"install -o root -g root -m 0700 -d {ETC}",
          f"install -o root -g root -m 0600 <policy.json> {POLICY}",
          f"install -o root -g root -m 0600 <attestation.key> {KEY}"],
         "operator-authored policy and key; never generated by an agent"),
        ("06_negative_canary_before_enabling",
         ["python3 " + str(LIBEXEC / "harness_delivery_controller.py") + " --plan ...  # held lane",
          "expect: decision=denied reason=release_lane_on_hold; zero docker/coolify calls in the log",
          "expect: unattested merge -> local_ci_attestation_missing; wrong UUID -> coolify_uuid_mismatch"],
         "all negative canaries denied before the timer is re-enabled"),
        ("07_enable_after_canary",
         ["systemctl start harness-image-delivery.timer",
          "systemctl is-active harness-image-delivery.timer",
          "tail -n 50 /var/lib/harness-image-delivery/delivery.log"],
         "canaries denied AND one authorized lane promoted with digest readback"),
        ("08_rollback",
         [f"systemctl stop harness-image-delivery.timer",
          f"install -o root -g root -m 0755 {backup} {LIBEXEC / 'harness_image_delivery.py'}",
          f"rm -f {LIBEXEC / 'harness_native_delivery.py'}",
          "systemctl start harness-image-delivery.timer"],
         "restores the hold-blind controller and the previous timer cadence"),
    ]
    return steps


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only preflight for the Harness delivery gate install")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--sha", required=True)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--probe", choices=("host",), default="host")
    args = parser.parse_args(argv)
    probe = Probe()
    try:
        checks, blockers, installed, expected = check(probe, args.repo, args.sha)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ready": False, "reason": str(exc)[:300]}), file=sys.stderr)
        return 1
    report = {"ready": not blockers, "sha": args.sha, "checks": checks,
              "blockers": blockers, "installed": installed, "expected_sha256": expected}
    if args.plan:
        # A plan is only emitted when the destructive preconditions hold; a
        # blocker is reported instead of an install recipe that would be unsafe.
        report["plan"] = install_plan(args.sha, expected) if not blockers else []
    print(json.dumps(report, sort_keys=True, indent=1))
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
