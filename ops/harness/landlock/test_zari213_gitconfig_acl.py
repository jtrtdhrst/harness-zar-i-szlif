#!/usr/bin/env python3
"""Fail-closed Landlock grants for the non-secret daemon Git helper config."""
import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).with_name("zari213-hermes-task-landlock.py")
spec = importlib.util.spec_from_file_location("zari213_landlock", SOURCE)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class GitConfigLandlockTests(unittest.TestCase):
    def test_regular_file_gets_only_requested_read_file_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / ".gitconfig"
            config.write_text("[credential]\n\thelper = /nonsecret/helper\n")
            with patch.object(policy, "checked_syscall") as call:
                policy.grant(123, config, policy.READ_FILE,
                             require_regular_nofollow=True)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(call.call_args.args[0], 445)

    def test_symlink_to_other_role_never_granted(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret = pathlib.Path(tmp) / "foreign-role"
            secret.write_text("sensitive")
            link = pathlib.Path(tmp) / ".gitconfig"
            link.symlink_to(secret)
            with patch.object(policy, "checked_syscall") as call:
                with self.assertRaises(ValueError):
                    policy.grant(123, link, policy.READ_FILE,
                                 require_regular_nofollow=True)
                call.assert_not_called()

    def test_directory_never_granted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(policy, "checked_syscall") as call:
                with self.assertRaises(ValueError):
                    policy.grant(123, tmp, policy.READ_FILE,
                                 require_regular_nofollow=True)
                call.assert_not_called()

    def test_missing_strict_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(policy, "checked_syscall") as call:
                with self.assertRaises(FileNotFoundError):
                    policy.grant(123, pathlib.Path(tmp) / ".gitconfig",
                                 policy.READ_FILE, require_regular_nofollow=True)
                call.assert_not_called()

    def test_existing_non_strict_missing_path_keeps_prior_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(policy, "checked_syscall") as call:
                policy.grant(123, pathlib.Path(tmp) / "missing", policy.READ_FILE)
                call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
