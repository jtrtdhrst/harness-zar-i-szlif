"""Fail-closed tests for the root-invoked Harness local-CI attester (ZARI-240).

Includes the negative controls demanded by the owner's exact-SHA security review
of PR #112: no caller-supplied argv, no caller-supplied repo path, and no test
execution under uid 0.
"""
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import harness_local_ci_attest as attest

KEY = b"k" * 32
OTHER_KEY = b"z" * 32
SOURCE = "a" * 40
BASE = "b" * 40
DIGEST = "sha256:" + "c" * 64
POLICY_DIGEST = "sha256:" + "e" * 64
RESULTS = [{"command": "/usr/bin/python3 -m unittest -q", "exit": 0}]
PATHS = ["mantic-mcp/src/server.ts"]
NONROOT = os.geteuid() or 1000


def policy(**overrides):
    base = {
        "schema_version": 1,
        "repo_root": "/usr",
        "out_dir": "/var/lib/paperclip-gitops/harness-attestations",
        "key_file": "/etc/paperclip-gitops/harness-attestation.key",
        "run_as_uid": NONROOT,
        "run_as_gid": os.getegid() or 1000,
        "services": {"mantic-mcp": [["/bin/sh", "-c", "exit 0"]]},
    }
    base.update(overrides)
    return base


class AttesterTests(unittest.TestCase):
    def build(self, **overrides):
        kwargs = {"service": "mantic-mcp", "source_sha": SOURCE, "results": RESULTS,
                  "changed_paths": PATHS, "image_digest": DIGEST, "key": KEY,
                  "runner_uid": NONROOT, "policy_digest": POLICY_DIGEST}
        kwargs.update(overrides)
        return attest.build_attestation(**kwargs)

    # --- signature / artifact integrity -------------------------------------
    def test_signature_roundtrip_verifies(self):
        self.assertTrue(attest.verify_attestation(self.build(), KEY))

    def test_tampered_payload_is_rejected(self):
        data = self.build()
        data["tests"] = [{"command": "/usr/bin/python3 -m unittest -q", "exit": 0},
                         {"command": "echo skipped", "exit": 0}]
        self.assertFalse(attest.verify_attestation(data, KEY))

    def test_wrong_key_is_rejected(self):
        self.assertFalse(attest.verify_attestation(self.build(), OTHER_KEY))

    def test_missing_or_malformed_signature_is_rejected(self):
        data = self.build()
        data.pop("signature")
        self.assertFalse(attest.verify_attestation(data, KEY))
        self.assertFalse(attest.verify_attestation("not-a-dict", KEY))
        self.assertFalse(attest.verify_attestation(self.build(), b"short"))

    def test_signature_field_is_the_only_unsigned_exclusion(self):
        data = self.build()
        self.assertIn("signature", data)
        self.assertNotIn("signature", attest.signed_payload(data))

    def test_rejects_failing_test_exit(self):
        with self.assertRaisesRegex(attest.Denied, "attestation_tests_failed"):
            self.build(results=[{"command": "/usr/bin/python3 -m unittest -q", "exit": 1}])

    def test_rejects_empty_test_evidence(self):
        with self.assertRaisesRegex(attest.Denied, "attestation_tests_missing"):
            self.build(results=[])

    def test_rejects_duplicate_test_records(self):
        with self.assertRaisesRegex(attest.Denied, "attestation_test_duplicate"):
            self.build(results=RESULTS + RESULTS)

    def test_rejects_changes_outside_the_service(self):
        with self.assertRaisesRegex(attest.Denied, "changed_paths_outside_service"):
            self.build(changed_paths=["paperclip-mcp/gitops/paperclip-mcp-auto-release.py"])

    def test_rejects_traversal_and_absolute_paths(self):
        for paths in (["mantic-mcp/../paperclip-mcp/x.py"], ["/etc/passwd"]):
            with self.assertRaises(attest.Denied):
                self.build(changed_paths=paths)

    def test_rejects_invalid_sha_and_digest(self):
        with self.assertRaisesRegex(attest.Denied, "invalid_source_sha"):
            self.build(source_sha="deadbeef")
        with self.assertRaisesRegex(attest.Denied, "invalid_image_digest"):
            self.build(image_digest="sha256:abc")

    def test_artifact_manifest_digest_ignores_timing(self):
        first = self.build(created_at="2026-11-16T00:00:00+00:00")
        second = self.build(created_at="2026-11-17T00:00:00+00:00")
        self.assertEqual(first["artifact_manifest_digest"], second["artifact_manifest_digest"])
        self.assertNotEqual(first["signature"], second["signature"])

    def test_idempotent_reuse_requires_identical_run_identity(self):
        data = self.build()
        self.assertTrue(attest.reusable(data, "mantic-mcp", SOURCE, DIGEST,
                                        ["/usr/bin/python3 -m unittest -q"], KEY, POLICY_DIGEST))
        self.assertFalse(attest.reusable(data, "mantic-mcp", "d" * 40, DIGEST,
                                         ["/usr/bin/python3 -m unittest -q"], KEY))
        self.assertFalse(attest.reusable(data, "mantic-mcp", SOURCE, DIGEST, ["pytest -q"], KEY))
        self.assertFalse(attest.reusable(data, "mantic-mcp", SOURCE, DIGEST,
                                         ["/usr/bin/python3 -m unittest -q"], OTHER_KEY))
        self.assertFalse(attest.reusable(data, "mantic-mcp", SOURCE, DIGEST,
                                         ["/usr/bin/python3 -m unittest -q"], KEY, "sha256:" + "f" * 64))

    def test_attestation_path_is_service_and_sha_scoped(self):
        path = attest.attestation_path("/var/lib/paperclip-gitops/out", "mantic-mcp", SOURCE)
        self.assertEqual(path, Path("/var/lib/paperclip-gitops/out") / ("mantic-mcp-" + SOURCE + ".json"))

    def test_atomic_write_is_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "attest.json"
            attest.write_atomic(target, self.build())
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(json.loads(target.read_text())["service"], "mantic-mcp")

    def test_atomic_attestation_write_never_follows_predictable_tmp_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "attest.json"
            victim = Path(tmp) / "victim"
            victim.write_text("leave untouched", encoding="utf-8")
            # Old implementation used attest.tmp with O_TRUNC, following
            # this link and destroying an unrelated file as root.
            (Path(tmp) / "attest.tmp").symlink_to(victim)
            attest.write_atomic(target, self.build())
            self.assertEqual(victim.read_text(encoding="utf-8"), "leave untouched")
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["service"],
                             "mantic-mcp")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_attestation_output_directory_must_be_root_private_and_not_a_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            out.mkdir()
            out.chmod(0o777)
            with self.assertRaisesRegex(attest.Denied, "attestation_output_dir_not_root_private"):
                attest.require_root_private_output_dir(out)
            out.chmod(0o700)
            alias = Path(tmp) / "alias"
            alias.symlink_to(out, target_is_directory=True)
            with self.assertRaisesRegex(attest.Denied, "attestation_output_dir_not_root_private"):
                attest.require_root_private_output_dir(alias)

    # --- no caller-supplied execution surface -------------------------------
    def test_cli_rejects_caller_supplied_test_commands(self):
        for argv in (["--test-command", '["/bin/sh","-c","id"]'], ["--repo", "/tmp"],
                     ["--out-dir", "/tmp"], ["--key-file", "/tmp/k"],
                     ["--policy", "/tmp/alternate-root-owned-policy.json"]):
            with self.assertRaises(SystemExit) as caught:
                attest.main(["--service", "mantic-mcp", "--source-sha", SOURCE,
                             "--base-sha", BASE, "--image-digest", DIGEST] + argv)
            self.assertEqual(caught.exception.code, 2, "CLI must not accept " + argv[0])

    def test_alternate_repo_path_is_not_accepted(self):
        self.assertNotIn("repo", attest.main.__doc__ or "")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(attest.Denied, "policy_repo_root_unavailable"):
                attest.validate_policy(policy(repo_root=str(Path(tmp) / "missing")))

    def test_policy_out_dir_outside_state_root_is_rejected(self):
        with self.assertRaisesRegex(attest.Denied, "policy_out_dir_outside_allowlist"):
            attest.validate_policy(policy(out_dir="/tmp/attestations"))

    def test_policy_relative_paths_are_rejected(self):
        for field in ("repo_root", "out_dir", "key_file"):
            with self.assertRaisesRegex(attest.Denied, "policy_" + field + "_invalid"):
                attest.validate_policy(policy(**{field: "relative/path"}))

    # --- uid 0 execution is refused ----------------------------------------
    def test_policy_requires_privilege_drop(self):
        for uid, gid in ((0, 1000), (1000, 0), (None, 1000), (1000, None), ("1000", 1000)):
            with self.assertRaisesRegex(attest.Denied, "policy_privilege_drop_missing"):
                attest.validate_policy(policy(run_as_uid=uid, run_as_gid=gid))

    def test_prctl_failure_denies_before_privilege_change(self):
        # A nonzero prctl return or syscall exception must never become a
        # silent PASS, and no uid/gid transition may occur afterwards.
        for outcome in ("negative", "exception", "missing"):
            with self.subTest(outcome=outcome):
                with patch("ctypes.CDLL") as cdll, \
                     patch.object(attest.os, "setsid"), \
                     patch.object(attest.os, "setgroups") as groups, \
                     patch.object(attest.os, "setgid") as setgid, \
                     patch.object(attest.os, "setuid") as setuid:
                    if outcome == "negative":
                        cdll.return_value.prctl.return_value = -1
                    elif outcome == "exception":
                        cdll.return_value.prctl.side_effect = OSError("blocked")
                    else:
                        del cdll.return_value.prctl
                    with self.assertRaisesRegex(OSError, "no_new_privs_unavailable"):
                        attest.privilege_dropper(NONROOT, os.getegid() or 1000)()
                    groups.assert_not_called()
                    setgid.assert_not_called()
                    setuid.assert_not_called()

    def test_prctl_success_allows_privilege_drop(self):
        with patch("ctypes.CDLL") as cdll, \
             patch.object(attest.os, "setsid"), \
             patch.object(attest.os, "setgroups") as groups, \
             patch.object(attest.os, "setgid") as setgid, \
             patch.object(attest.os, "setuid") as setuid, \
             patch.object(attest.os, "geteuid", return_value=NONROOT), \
             patch.object(attest.os, "getuid", return_value=NONROOT):
            cdll.return_value.prctl.return_value = 0
            attest.privilege_dropper(NONROOT, os.getegid() or 1000)()
            groups.assert_called_once_with([])
            setgid.assert_called_once()
            setuid.assert_called_once_with(NONROOT)

    def test_run_tests_refuses_uid_zero(self):
        for uid in (0, None, -1, True, 1000.0):
            with self.assertRaisesRegex(attest.Denied, "test_runner_privilege_not_dropped"):
                attest.run_tests([["/bin/sh", "-c", "exit 0"]], ".", uid, 1000)

    def test_run_tests_refuses_uid_zero_gid(self):
        with self.assertRaisesRegex(attest.Denied, "test_runner_privilege_not_dropped"):
            attest.run_tests([["/bin/sh", "-c", "exit 0"]], ".", NONROOT, 0)

    def test_privilege_dropper_refuses_uid_zero(self):
        with self.assertRaisesRegex(attest.Denied, "test_runner_privilege_not_dropped"):
            attest.privilege_dropper(0, 1000)
        with self.assertRaisesRegex(attest.Denied, "test_runner_privilege_not_dropped"):
            attest.privilege_dropper(1000, 0)

    def test_attestation_cannot_claim_a_root_test_runner(self):
        for runner in (0, None, -1, True):
            with self.assertRaisesRegex(attest.Denied, "test_runner_privilege_not_dropped"):
                self.build(runner_uid=runner)

    def test_attestation_requires_policy_digest(self):
        for digest in (None, "", "sha256:abc", 42):
            with self.assertRaisesRegex(attest.Denied, "policy_digest_missing"):
                self.build(policy_digest=digest)

    @unittest.skipIf(os.geteuid() == 0, "root cannot demonstrate an unprivileged runner")
    def test_run_tests_records_real_exit_codes_as_unprivileged_uid(self):
        results = attest.run_tests([["/bin/sh", "-c", "exit 0"], ["/bin/sh", "-c", "exit 3"]],
                                   ".", os.geteuid(), os.getegid())
        self.assertEqual([r["exit"] for r in results], [0, 3])

    def test_run_tests_fails_closed_when_uid_cannot_be_assumed(self):
        other = 65534 if os.geteuid() != 65534 else 65533
        with self.assertRaisesRegex(attest.Denied, "test_runner_uid_unavailable"):
            attest.run_tests([["/bin/sh", "-c", "exit 0"]], ".", other, os.getegid())

    def test_run_tests_fails_closed_on_missing_binary(self):
        with self.assertRaisesRegex(attest.Denied, "test_command_unavailable"):
            attest.run_tests([["/definitely-not-a-real-binary-xyz"]], ".",
                             os.geteuid() or 1000, os.getegid() or 1000)

    def test_environment_is_sanitized(self):
        env = attest.sanitized_env("/home/runner")
        self.assertEqual(set(env), {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"})
        self.assertEqual(env["HOME"], "/home/runner")

    # --- policy-declared command allowlist ---------------------------------
    def test_service_must_be_declared_in_policy(self):
        with self.assertRaisesRegex(attest.Denied, "service_not_in_policy"):
            attest.policy_commands(policy(), "playwright-mcp")

    def test_command_must_be_absolute(self):
        with self.assertRaisesRegex(attest.Denied, "policy_command_not_absolute"):
            attest.policy_commands(policy(services={"mantic-mcp": [["python3", "-m", "unittest"]]}), "mantic-mcp")

    def test_command_count_is_bounded(self):
        with self.assertRaisesRegex(attest.Denied, "policy_commands_invalid"):
            attest.policy_commands(policy(services={"mantic-mcp": []}), "mantic-mcp")

    def test_policy_services_must_exist(self):
        with self.assertRaisesRegex(attest.Denied, "policy_services_missing"):
            attest.validate_policy(policy(services={}))

    # --- checked-out tree -----------------------------------------------
    def test_checkout_must_be_at_the_source_sha(self):
        head = type("R", (), {"returncode": 0, "stdout": "f" * 40 + "\n"})()
        clean = type("R", (), {"returncode": 0, "stdout": ""})()
        with patch.object(attest.subprocess, "run", side_effect=[head, clean]):
            with self.assertRaisesRegex(attest.Denied, "checkout_not_at_source_sha"):
                attest.verify_checkout(".", SOURCE)

    def test_checkout_must_be_clean(self):
        head = type("R", (), {"returncode": 0, "stdout": SOURCE + "\n"})()
        dirty = type("R", (), {"returncode": 0, "stdout": " M scripts/x.py\n"})()
        with patch.object(attest.subprocess, "run", side_effect=[head, dirty]):
            with self.assertRaisesRegex(attest.Denied, "checkout_dirty"):
                attest.verify_checkout(".", SOURCE)
        with patch.object(attest.subprocess, "run", side_effect=[head, clean_result()]):
            self.assertTrue(attest.verify_checkout(".", SOURCE))

    def test_changed_paths_uses_git_and_fails_closed(self):
        completed = type("R", (), {"returncode": 0, "stdout": "mantic-mcp/a.ts\nmantic-mcp/b.ts\n"})()
        with patch.object(attest.subprocess, "run", return_value=completed):
            self.assertEqual(attest.changed_paths(".", BASE, SOURCE), ["mantic-mcp/a.ts", "mantic-mcp/b.ts"])
        for result, reason in ((type("R", (), {"returncode": 0, "stdout": ""})(), "changed_paths_unbounded"),
                               (type("R", (), {"returncode": 128, "stdout": ""})(), "git_diff_failed")):
            with patch.object(attest.subprocess, "run", return_value=result):
                with self.assertRaisesRegex(attest.Denied, reason):
                    attest.changed_paths(".", BASE, SOURCE)

    # --- trusted file loading (symlink / TOCTOU / ownership) ---------------
    def test_trusted_file_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "key"
            real.write_bytes(KEY)
            os.chmod(real, 0o600)
            link = Path(tmp) / "link"
            link.symlink_to(real)
            with self.assertRaisesRegex(attest.Denied, "signing_key_unavailable"):
                attest.read_trusted_file(link, "signing_key", require_root=False)

    def test_trusted_file_rejects_world_writable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key"
            path.write_bytes(KEY)
            os.chmod(path, 0o666)
            with self.assertRaisesRegex(attest.Denied, "signing_key_world_writable"):
                attest.read_trusted_file(path, "signing_key", require_root=False)

    def test_trusted_file_rejects_non_root_owner_when_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key"
            path.write_bytes(KEY)
            os.chmod(path, 0o600)
            if os.geteuid() == 0:
                self.assertEqual(attest.read_trusted_file(path, "signing_key"), KEY)
            else:
                with self.assertRaisesRegex(attest.Denied, "signing_key_not_root_owned"):
                    attest.read_trusted_file(path, "signing_key")

    def test_fixed_policy_symlink_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "policy.json"
            real.write_text("{}")
            os.chmod(real, 0o600)
            alias = Path(tmp) / "policy-alias"
            alias.symlink_to(real)
            with patch.object(attest, "DEFAULT_POLICY", alias):
                self.assertEqual(attest.main([
                    "--service", "mantic-mcp", "--source-sha", SOURCE,
                    "--base-sha", BASE, "--image-digest", DIGEST, "--dry-run"
                ]), 1)

    def test_trusted_file_reads_without_following_a_swap(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key"
            path.write_bytes(KEY)
            os.chmod(path, 0o600)
            self.assertEqual(attest.read_trusted_file(path, "signing_key", require_root=False), KEY)

    def test_weak_key_is_rejected(self):
        with self.assertRaisesRegex(attest.Denied, "signing_key_weak"):
            attest.sign({"schema_version": 1}, b"short")

    # --- dry run ------------------------------------------------------------
    def test_dry_run_writes_nothing_and_uses_policy_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            # A dry-run must be able to inspect the plan without opening
            # or requiring the privileged signing secret.
            key_file = Path(tmp) / "missing-signing-key"
            out = Path(tmp) / "out"
            manifest = policy(repo_root=str(root), out_dir=str(out), key_file=str(key_file),
                              services={"mantic-mcp": [["/bin/sh", "-c", "exit 0"]]})
            policy_path = Path(tmp) / "policy.json"
            policy_path.write_text(json.dumps(manifest))
            os.chmod(policy_path, 0o600)
            stream = io.StringIO()
            with patch.object(attest, "STATE_ROOT", tmp), \
                    patch.object(attest, "changed_paths", return_value=PATHS), \
                    patch.object(attest, "DEFAULT_POLICY", policy_path), \
                    patch("sys.stdout", stream):
                code = attest.main(["--service", "mantic-mcp", "--source-sha", SOURCE,
                                    "--base-sha", BASE, "--image-digest", DIGEST,
                                    "--dry-run"])
            self.assertEqual(code, 0)
            self.assertFalse(out.exists(), "dry run must not create or write attestations")
            self.assertFalse(key_file.exists(), "dry run must not need or create the signing key")
            printed = json.loads(stream.getvalue())
            self.assertEqual(printed["commands"], ["/bin/sh -c exit 0"])
            self.assertEqual(printed["runner_uid"], NONROOT)


def clean_result():
    return type("R", (), {"returncode": 0, "stdout": ""})()


if __name__ == "__main__":
    unittest.main()
