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
import importlib.util
import json
import os
import shlex
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
UNIT = Path("/etc/systemd/system") / SERVICE
REVIEWED_UNIT = "ops/systemd/" + SERVICE
ADAPTER = "harness_native_delivery.py"
BASELINE = STATE / "delivery" / "auto-main.json"
CHECKOUT = STATE / "checkout"
GATES = STATE / "gates"
MODULES = ("harness_release_admission.py", "harness_local_ci_attest.py",
           "harness_delivery_controller.py", "harness_native_delivery.py")
UNITS = (REVIEWED_UNIT,)


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

    def read(self, path):
        """Text of a small config file (systemd unit), or None when unreadable."""
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def euid(self):
        return os.geteuid()


def parse_execstart(unit_text):
    """Return the argv a unit's ``ExecStart`` would run (continuations joined).

    systemd starts the program directly - there is no shell - so the line is
    split with shell-like quoting rules but never evaluated. Comments and every
    other directive are ignored.
    """
    lines, buffer = [], ""
    for raw in (unit_text or "").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        buffer = (buffer + " " + stripped).strip() if buffer else stripped
        if buffer.endswith("\\"):
            buffer = buffer[:-1].strip()
            continue
        lines.append(buffer)
        buffer = ""
    if buffer:
        lines.append(buffer)
    for line in lines:
        if not line.startswith("ExecStart="):
            continue
        body = line.split("=", 1)[1].strip()
        if body.startswith("-"):        # systemd's ignore-failure prefix
            body = body[1:].strip()
        try:
            return shlex.split(body)
        except ValueError:
            return []
    return []


def adapter_parser(script_path):
    """Load ``build_parser`` from the adapter file the unit actually runs.

    The module is executed from the path in ``ExecStart``, so the check validates
    the installed adapter, not a repository copy. Importing is side-effect free:
    the adapter reads no secret at import time.
    """
    script = Path(script_path)
    if not script.is_file():
        raise ImportError("adapter missing")
    parent = str(script.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    spec = importlib.util.spec_from_file_location("_harness_adapter_under_test", script)
    if spec is None or spec.loader is None:
        raise ImportError("adapter not loadable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_parser()


def execstart_problem(argv):
    """None when the adapter's own parser accepts this invocation, else a reason.

    This is the wiring gate: an installed ``ExecStart`` the adapter would reject
    (as the legacy ``--auto``-only invocation was) can never be reported ready.
    """
    if len(argv) < 2:
        return "execstart_missing_or_unparsable"
    script, rest = argv[1], argv[2:]
    if Path(script).name != ADAPTER:
        return "execstart_runs_the_hold_blind_controller"
    try:
        adapter_parser(script).parse_args(rest)
    except SystemExit:
        return "adapter_rejects_execstart_arguments"
    except (ImportError, OSError, AttributeError):
        return "adapter_not_importable"
    return None


def blob_sha256(repo, sha, path):
    """sha256 of one file as committed at an exact SHA (no checkout needed)."""
    completed = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{path}"],
                               capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(f"cannot read {path} at {sha}")
    import hashlib

    return hashlib.sha256(completed.stdout).hexdigest()


def expected_hashes(repo, sha, modules=MODULES, units=UNITS):
    """Immutable expected digests for the modules and units approved at ``sha``."""
    digests = {name: blob_sha256(repo, sha, f"scripts/{name}") for name in modules}
    digests.update({unit: blob_sha256(repo, sha, unit) for unit in units})
    return digests


def check(probe, repo, sha):
    """Return ``(checks, blockers, installed, expected, pending)``. Read-only.

    ``blockers`` are conditions that must hold before any install step is safe or
    meaningful. ``pending`` are assertions the install itself satisfies (the
    reviewed unit is not wired yet, for example): they must all pass before the
    host is reported ready, but they must not stop the plan that fixes them.
    """
    checks, blockers, pending = {}, [], []

    def record(name, ok, detail):
        checks[name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            blockers.append(name)

    def install_assertion(name, ok, detail, host_already_wired):
        checks[name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            (blockers if host_already_wired else pending).append(name)

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

    # The wiring the timer actually executes. The unit is what used to drift:
    # the timer ran the hold-blind controller's `--auto` invocation while the
    # reviewed adapter required --base-sha/--source-sha and exited 2.
    unit_info = probe.stat(UNIT)
    unit_text = probe.read(UNIT) if unit_info["exists"] else None
    argv = parse_execstart(unit_text) if unit_text else []
    wired_to_adapter = len(argv) > 1 and Path(argv[1]).name == ADAPTER
    problem = execstart_problem(argv) if argv else "unit_not_installed"
    install_assertion("delivery_unit_wired", problem is None,
                      problem or " ".join(argv), wired_to_adapter)
    expected_unit = expected.get(REVIEWED_UNIT)
    unit_digest = probe.sha256(UNIT) if unit_info["exists"] else None
    install_assertion("delivery_unit_matches_approved_sha",
                      bool(expected_unit) and unit_digest == expected_unit,
                      "installed=%s expected=%s" % (unit_digest, expected_unit),
                      wired_to_adapter)
    if unit_info["exists"]:
        record("delivery_unit_root_owned", unit_info["uid"] == 0,
               f"uid={unit_info['uid']} mode={oct(unit_info['mode'] or 0)}")

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
    return checks, blockers, installed, expected, pending


def install_plan(sha, expected):
    """Ordered operator steps; each tuple is (step, command(s), precondition)."""
    backup = STATE / "backups" / f"harness_image_delivery-{sha[:12]}.py"
    unit_digest = expected.get(REVIEWED_UNIT, "<reviewed-unit-sha256>")
    steps = [
        ("01_stop_timer",
         ["systemctl stop harness-image-delivery.timer", "systemctl stop harness-image-delivery.service"],
         "timer and oneshot service inactive; delivery lock unheld"),
        ("02_backup_legacy_controller_and_unit",
         [f"install -o root -g root -m 0600 {LIBEXEC / 'harness_image_delivery.py'} {backup}",
          f"sha256sum {LIBEXEC / 'harness_image_delivery.py'} {backup}",
          f"install -o root -g root -m 0600 {UNIT} {STATE / 'backups' / ('harness-image-delivery.service-' + sha[:12] + '.bak')}"],
         "legacy_controller_present_to_back_up"),
        ("03_stage_modules",
         [f"git -C <repo> show {sha}:scripts/{name} | install -o root -g root -m 0644 /dev/stdin {LIBEXEC / name}"
          for name in MODULES],
         "approved_sha_present"),
        ("04_verify_staged_hashes",
         [f"test \"$(sha256sum {LIBEXEC / name} | cut -d' ' -f1)\" = {expected[name]}" for name in MODULES]
         + [f"test \"$(sha256sum {UNIT} | cut -d' ' -f1)\" = {unit_digest}"],
         "every installed module and the reviewed unit match the approved SHA digest"),
        ("05_install_policy_and_key",
         [f"install -o root -g root -m 0700 -d {ETC}",
          f"install -o root -g root -m 0600 <policy.json> {POLICY}",
          f"install -o root -g root -m 0600 <attestation.key> {KEY}"],
         "operator-authored policy and key; never generated by an agent"),
        ("06_install_reviewed_unit_and_reload",
         [f"git -C <repo> show {sha}:{REVIEWED_UNIT} | install -o root -g root -m 0644 /dev/stdin {UNIT}",
          "systemctl daemon-reload",
          f"systemctl cat {SERVICE} | sed -n '/^ExecStart=/p'",
          f"install -o root -g root -m 0700 -d {CHECKOUT} {GATES}"],
         "ExecStart must name /usr/local/libexec/harness_native_delivery.py with "
         "--mode deploy --auto; the preflight re-check must report delivery_unit_wired ok"),
        ("07_negative_canary_before_enabling",
         ["python3 " + str(LIBEXEC / "harness_delivery_controller.py") + " --plan ...  # held lane",
          "expect: decision=denied reason=release_lane_on_hold; zero docker/coolify calls in the log",
          "expect: unattested merge -> local_ci_attestation_missing; wrong UUID -> coolify_uuid_mismatch",
          "expect: python3 /usr/local/libexec/harness_native_delivery.py --mode plan --auto "
          "-> no_change or denied with zero docker/coolify calls"],
         "all negative canaries denied before the timer is re-enabled"),
        ("08_enable_after_canary",
         ["systemctl start harness-image-delivery.timer",
          "systemctl is-active harness-image-delivery.timer",
          "tail -n 50 /var/lib/harness-image-delivery/delivery.log"],
         "canaries denied AND one authorized lane promoted with digest readback"),
        ("09_rollback",
         [f"systemctl stop harness-image-delivery.timer",
          f"install -o root -g root -m 0755 {backup} {LIBEXEC / 'harness_image_delivery.py'}",
          f"install -o root -g root -m 0644 {STATE / 'backups' / ('harness-image-delivery.service-' + sha[:12] + '.bak')} {UNIT}",
          "systemctl daemon-reload",
          "systemctl start harness-image-delivery.timer"],
         "restores the hold-blind controller, its unit and the previous timer cadence"),
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
        checks, blockers, installed, expected, pending = check(probe, args.repo, args.sha)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ready": False, "reason": str(exc)[:300]}), file=sys.stderr)
        return 1
    report = {"ready": not blockers and not pending, "sha": args.sha, "checks": checks,
              "blockers": blockers, "pending": pending, "installed": installed,
              "expected_sha256": expected}
    if args.plan:
        # A plan is only emitted when the destructive preconditions hold; a
        # blocker is reported instead of an install recipe that would be unsafe.
        report["plan"] = install_plan(args.sha, expected) if not blockers else []
    print(json.dumps(report, sort_keys=True, indent=1))
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
