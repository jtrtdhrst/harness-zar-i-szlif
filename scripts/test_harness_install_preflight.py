"""Tests for the read-only Harness delivery install preflight (ZARI-240).

The preflight is the source-side half of the OPERATOR_ONLY install: it must never
produce a green light, or an install plan, unless the timer is stopped, the
installed modules match the exact approved SHA and every privileged file is
root-owned. These tests use a fake probe; nothing here touches a real unit.
"""
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import harness_install_preflight as preflight

REPO = str(Path(__file__).resolve().parent.parent)


def head_sha():
    return subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


SHA = head_sha()
# One digest is read from a real committed blob; the rest are synthetic so the
# preflight logic is testable while the current working tree is uncommitted.
REAL_BLOB = preflight.blob_sha256(REPO, SHA, "scripts/harness_release_admission.py")
EXPECTED = {name: (REAL_BLOB if name == "harness_release_admission.py" else "d" * 64)
            for name in preflight.MODULES}
EXPECTED[preflight.REVIEWED_UNIT] = "e" * 64

ADAPTER = str(Path(REPO) / "scripts" / "harness_native_delivery.py")
REVIEWED_UNIT_TEXT = f"""[Unit]
Description=test unit
# ExecStart is what the timer really runs
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {ADAPTER} --mode deploy --auto \
  --artifact-dir /var/lib/harness-image-delivery/gates
Nice=10
"""

LEGACY_UNIT_TEXT = """[Service]
ExecStart=/usr/bin/python3 /usr/local/libexec/harness_image_delivery.py --auto
"""


class FakeProbe:
    def __init__(self, active=(), euid=0, files=None):
        self.active = set(active)
        self.uid = euid
        self.files = dict(files or {})

    def is_active(self, unit):
        return unit in self.active

    def stat(self, path):
        entry = self.files.get(str(path))
        if not entry:
            return {"exists": False, "uid": None, "mode": None}
        return {"exists": True, "uid": entry.get("uid", 0), "mode": entry.get("mode", 0o644)}

    def sha256(self, path):
        entry = self.files.get(str(path))
        return entry.get("sha256") if entry else None

    def read(self, path):
        entry = self.files.get(str(path))
        return entry.get("text") if entry else None

    def euid(self):
        return self.uid


def installed_files(**overrides):
    files = {}
    for name, digest in EXPECTED.items():
        files[str(preflight.LIBEXEC / name)] = {"uid": 0, "mode": 0o644, "sha256": digest}
    files[str(preflight.LIBEXEC / "harness_image_delivery.py")] = {"uid": 0, "mode": 0o755,
                                                                   "sha256": "a" * 64}
    files[str(preflight.POLICY)] = {"uid": 0, "mode": 0o600}
    files[str(preflight.KEY)] = {"uid": 0, "mode": 0o600}
    files[str(preflight.STATE)] = {"uid": 0, "mode": 0o755}
    files[str(preflight.SOURCE_RANGE)] = {"uid": 0, "mode": 0o600}
    files[str(preflight.UNIT)] = {"uid": 0, "mode": 0o644,
                                  "sha256": EXPECTED[preflight.REVIEWED_UNIT],
                                  "text": REVIEWED_UNIT_TEXT}
    files.update({key: {**value, **overrides.get(key, {})} for key, value in files.items()})
    return files


class PreflightTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(preflight, "expected_hashes", lambda repo, sha, modules=None: dict(EXPECTED))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_expected_hashes_bind_the_approved_sha(self):
        self.assertEqual(sorted(EXPECTED),
                         sorted(preflight.MODULES + preflight.UNITS))
        for digest in EXPECTED.values():
            self.assertRegex(digest, r"^[a-f0-9]{64}$")
        self.assertEqual(len(REAL_BLOB), 64)
        self.assertNotEqual(REAL_BLOB, "d" * 64)

    def test_blob_sha256_reads_the_exact_committed_file(self):
        digest = preflight.blob_sha256(REPO, SHA, "scripts/harness_release_admission.py")
        self.assertEqual(digest, REAL_BLOB)
        with self.assertRaises(RuntimeError):
            preflight.blob_sha256(REPO, SHA, "scripts/does-not-exist.py")

    def test_ready_when_timer_stopped_and_everything_root_owned(self):
        probe = FakeProbe(files=installed_files())
        checks, blockers, installed, expected, pending = preflight.check(probe, REPO, SHA)
        self.assertEqual(blockers, [])
        self.assertTrue(all(checks.values()), checks)
        self.assertEqual(expected, EXPECTED)
        self.assertEqual(installed["harness_delivery_controller.py"]["uid"], 0)

    def test_active_timer_blocks_the_install(self):
        probe = FakeProbe(active={preflight.TIMER}, files=installed_files())
        checks, blockers, _, _, _ = preflight.check(probe, REPO, SHA)
        self.assertIn("timer_inactive", blockers)
        self.assertFalse(checks["timer_inactive"]["ok"])

    def test_running_service_blocks_the_install(self):
        probe = FakeProbe(active={preflight.SERVICE}, files=installed_files())
        _, blockers, _, _, _ = preflight.check(probe, REPO, SHA)
        self.assertIn("service_inactive", blockers)

    def test_non_root_operator_is_reported(self):
        probe = FakeProbe(euid=997, files=installed_files())
        _, blockers, _, _, _ = preflight.check(probe, REPO, SHA)
        self.assertIn("operator_root", blockers)

    def test_mismatched_installed_module_is_a_blocker(self):
        files = installed_files()
        files[str(preflight.LIBEXEC / "harness_release_admission.py")]["sha256"] = "b" * 64
        _, blockers, _, _, _ = preflight.check(FakeProbe(files=files), REPO, SHA)
        self.assertIn("harness_release_admission.py_matches_approved_sha", blockers)

    def test_non_root_owned_installed_module_is_a_blocker(self):
        files = installed_files()
        files[str(preflight.LIBEXEC / "harness_delivery_controller.py")]["uid"] = 997
        _, blockers, _, _, _ = preflight.check(FakeProbe(files=files), REPO, SHA)
        self.assertIn("harness_delivery_controller.py_root_owned", blockers)

    def test_world_readable_policy_is_a_blocker(self):
        files = installed_files(**{str(preflight.POLICY): {"mode": 0o644}})
        _, blockers, _, _, _ = preflight.check(FakeProbe(files=files), REPO, SHA)
        self.assertIn("policy_root_private", blockers)

    def test_missing_legacy_controller_blocks_the_backup_step(self):
        files = installed_files()
        files.pop(str(preflight.LIBEXEC / "harness_image_delivery.py"))
        _, blockers, _, _, _ = preflight.check(FakeProbe(files=files), REPO, SHA)
        self.assertIn("legacy_controller_present_to_back_up", blockers)

    def test_empty_host_is_not_ready(self):
        _, blockers, _, _, _ = preflight.check(FakeProbe(files={}), REPO, SHA)
        self.assertIn("legacy_controller_present_to_back_up", blockers)
        self.assertNotIn("policy_present", blockers)
        self.assertNotIn("attestation_key_present", blockers)
        self.assertNotIn("state_dir_present", blockers)

    def test_plan_starts_with_the_timer_stop_and_ends_with_rollback(self):
        steps = preflight.install_plan(SHA, EXPECTED)
        self.assertEqual(steps[0][0], "01_stop_timer")
        self.assertIn("systemctl stop harness-image-delivery.timer", steps[0][1])
        self.assertEqual(steps[-1][0], "09_rollback")
        canary = [step for step in steps if step[0].startswith("07_")][0]
        self.assertTrue(any("denied" in line for line in canary[1]))
        verify = [step for step in steps if step[0].startswith("04_")][0]
        self.assertEqual(len(verify[1]), len(preflight.MODULES),
                         "only staged modules may be verified before unit installation")
        unit_step = [step for step in steps if step[0].startswith("06_")][0]
        self.assertTrue(any("daemon-reload" in line for line in unit_step[1]))
        self.assertTrue(any(str(preflight.UNIT) in line for line in unit_step[1]))
        self.assertTrue(any("sha256sum" in line and str(preflight.UNIT) in line
                            for line in unit_step[1]), "verify unit only after staging")
        self.assertTrue(any("install -o root -g root -m 0700 -d" in line
                            for line in steps[1][1]), "backup directory must be created")
        rollback = steps[-1][1]
        self.assertFalse(any("systemctl start" in line for line in rollback),
                         "rollback must never restart the HOLD-blind controller")
        self.assertTrue(any("systemctl stop" in line for line in rollback))

    def test_missing_installable_artifacts_are_pending_not_plan_blockers(self):
        files = installed_files()
        for path in (preflight.POLICY, preflight.KEY, preflight.STATE,
                     preflight.SOURCE_RANGE):
            files.pop(str(path))
        probe = FakeProbe(files=files)
        checks, blockers, _, _, pending = preflight.check(probe, REPO, SHA)
        self.assertEqual(blockers, [])
        for item in ("policy_present", "attestation_key_present",
                     "state_dir_present", "source_range_present"):
            self.assertIn(item, pending)
            self.assertFalse(checks[item]["ok"])
        with patch.object(preflight, "Probe", lambda: probe):
            with patch("sys.stdout", new_callable=lambda: __import__("io").StringIO()) as out:
                code = preflight.main(["--repo", REPO, "--sha", SHA, "--plan"])
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertFalse(payload["ready"])
        self.assertEqual(len(payload["plan"]), 9)

    def test_main_emits_no_plan_while_a_blocker_exists(self):
        probe = FakeProbe(active={preflight.TIMER}, files=installed_files())
        with patch.object(preflight, "Probe", lambda: probe):
            with patch("sys.stdout", new_callable=lambda: __import__("io").StringIO()) as out:
                code = preflight.main(["--repo", REPO, "--sha", SHA, "--plan"])
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(payload["ready"])
        self.assertEqual(payload["plan"], [])
        self.assertIn("timer_inactive", payload["blockers"])

    def test_main_emits_a_plan_when_ready(self):
        probe = FakeProbe(files=installed_files())
        with patch.object(preflight, "Probe", lambda: probe):
            with patch("sys.stdout", new_callable=lambda: __import__("io").StringIO()) as out:
                code = preflight.main(["--repo", REPO, "--sha", SHA, "--plan"])
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["plan"][0][0], "01_stop_timer")
        self.assertEqual(len(payload["plan"]), 9)


class UnitWiringTests(unittest.TestCase):
    """The timer's ExecStart must be an invocation the reviewed adapter accepts."""

    def setUp(self):
        patcher = patch.object(preflight, "expected_hashes",
                               lambda repo, sha, modules=None, units=None: dict(EXPECTED))
        patcher.start()
        self.addCleanup(patcher.stop)

    def files(self, text=REVIEWED_UNIT_TEXT, digest=None, uid=0):
        files = installed_files()
        files[str(preflight.UNIT)] = {"uid": uid, "mode": 0o644,
                                      "sha256": digest or EXPECTED[preflight.REVIEWED_UNIT],
                                      "text": text}
        return files

    def test_parse_execstart_joins_continuations_and_ignores_comments(self):
        argv = preflight.parse_execstart(REVIEWED_UNIT_TEXT)
        self.assertEqual(argv[0], "/usr/bin/python3")
        self.assertEqual(Path(argv[1]).name, preflight.ADAPTER)
        self.assertIn("--mode", argv)
        self.assertNotIn("#", " ".join(argv))

    def test_a_missing_execstart_is_reported(self):
        self.assertEqual(preflight.parse_execstart("[Service]\nNice=10\n"), [])

    def test_the_reviewed_unit_passes_the_adapter_parser(self):
        argv = preflight.parse_execstart(REVIEWED_UNIT_TEXT)
        self.assertIsNone(preflight.execstart_problem(argv))

    def test_an_argument_the_adapter_rejects_is_detected(self):
        # This is exactly the d3f4055 defect: the timer's invocation was not an
        # invocation the adapter could parse, and nothing checked it.
        argv = [ "/usr/bin/python3", ADAPTER, "--mode", "promote" ]
        self.assertEqual(preflight.execstart_problem(argv),
                         "adapter_rejects_execstart_arguments")

    def test_the_hold_blind_controller_is_detected(self):
        argv = ["/usr/bin/python3", "/usr/local/libexec/harness_image_delivery.py", "--auto"]
        self.assertEqual(preflight.execstart_problem(argv),
                         "execstart_runs_the_hold_blind_controller")

    def test_an_unwired_legacy_unit_is_pending_not_a_blocker(self):
        # The legacy unit is what the install replaces, so it must not stop the
        # plan that fixes it - but it must keep the host from being "ready".
        probe = FakeProbe(files=self.files(text=LEGACY_UNIT_TEXT))
        checks, blockers, _, _, pending = preflight.check(probe, REPO, SHA)
        self.assertNotIn("delivery_unit_wired", blockers)
        self.assertIn("delivery_unit_wired", pending)
        self.assertFalse(checks["delivery_unit_wired"]["ok"])
        with patch.object(preflight, "Probe", lambda: probe):
            with patch("sys.stdout", new_callable=lambda: __import__("io").StringIO()) as out:
                code = preflight.main(["--repo", REPO, "--sha", SHA, "--plan"])
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0, "a pending install assertion must not suppress the plan")
        self.assertEqual(len(payload["plan"]), 9)
        self.assertFalse(payload["ready"])

    def test_a_half_wired_unit_blocks_the_host(self):
        # A unit that already names the adapter but the adapter rejects is a host
        # fault, not something the install will cure.
        text = f"[Service]\nExecStart=/usr/bin/python3 {ADAPTER} --mode promote\n"
        probe = FakeProbe(files=self.files(text=text))
        _, blockers, _, _, pending = preflight.check(probe, REPO, SHA)
        self.assertIn("delivery_unit_wired", blockers)
        self.assertNotIn("delivery_unit_wired", pending)

    def test_a_unit_that_differs_from_the_approved_sha_is_reported(self):
        probe = FakeProbe(files=self.files(digest="f" * 64))
        _, blockers, _, _, pending = preflight.check(probe, REPO, SHA)
        self.assertIn("delivery_unit_matches_approved_sha", blockers)

    def test_fully_installed_host_is_ready(self):
        probe = FakeProbe(files=self.files())
        checks, blockers, _, _, pending = preflight.check(probe, REPO, SHA)
        self.assertEqual((blockers, pending), ([], []))
        self.assertTrue(checks["delivery_unit_wired"]["ok"])
        self.assertTrue(checks["delivery_unit_matches_approved_sha"]["ok"])


if __name__ == "__main__":
    unittest.main()
