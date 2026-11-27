#!/usr/bin/env python3
"""Never leak a provider-issued GitHub writer grant on validation/persist errors.

All provider calls are mocked; no production token or network access.
"""
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location(
    "zari263_writer_postissue", HERE/"multica-zar-github-app-refresh.py")
refresh=importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)

ISSUED="ghs_" + "N"*60


def grant():
    return {
        "status":201,
        "app_id":refresh.APP_ID,
        "installation_id":refresh.INSTALLATION_ID,
        "permissions":refresh.ROLE_PERMISSIONS[refresh.WRITER_ROLE],
        "repositories":list(refresh.REPOS),
        "token":ISSUED,
        "expires_at":"2099-01-01T00:00:00Z",
    }


class MintPostIssueSafety(unittest.TestCase):
    def run_mint(self, altered):
        result=types.SimpleNamespace(returncode=0,stdout=json.dumps(altered),stderr="")
        with patch.object(refresh.subprocess,"run",return_value=result), \
             patch.object(refresh,"revoke_new_writer_token",return_value=True) as revoke:
            with self.assertRaises(refresh.WriterGrantPostIssueError):
                refresh.mint(refresh.WRITER_ROLE)
            revoke.assert_called_once_with(ISSUED)

    def test_wrong_repository_scope_revokes_new_not_stale_token(self):
        wrong=grant()
        wrong["repositories"]=["attacker/other-repo"]
        self.run_mint(wrong)

    def test_wrong_permissions_revokes_new_token(self):
        wrong=grant()
        wrong["permissions"]={"contents":"write"}
        self.run_mint(wrong)

    def test_wrong_app_identity_revokes_new_token(self):
        wrong=grant()
        wrong["app_id"]=123
        self.run_mint(wrong)

    def test_short_expiry_revokes_new_token(self):
        wrong=grant()
        wrong["expires_at"]="2020-01-01T00:00:00Z"
        self.run_mint(wrong)

    def test_missing_expiry_revokes_new_token(self):
        wrong=grant()
        wrong.pop("expires_at")
        self.run_mint(wrong)

    def test_revoke_failure_surfaces_hard_error_no_secret(self):
        wrong=grant()
        wrong["permissions"]={"contents":"write"}
        with patch.object(refresh.subprocess,"run",return_value=types.SimpleNamespace(
             returncode=0,stdout=json.dumps(wrong),stderr="")), \
             patch.object(refresh,"revoke_new_writer_token",
                          side_effect=RuntimeError("synthetic provider 503")) as revoke:
            with self.assertRaisesRegex(refresh.WriterGrantPostIssueError,
                                        "revocation unconfirmed") as ctx:
                refresh.mint(refresh.WRITER_ROLE)
        self.assertNotIn(ISSUED, str(ctx.exception))
        revoke.assert_called_once_with(ISSUED)

    def test_nonzero_exit_after_issuance_still_revokes_returned_token(self):
        response = types.SimpleNamespace(returncode=1,stdout=json.dumps(grant()),stderr="")
        with patch.object(refresh.subprocess,"run",return_value=response), \
             patch.object(refresh,"revoke_new_writer_token",return_value=True) as revoke:
            with self.assertRaisesRegex(refresh.WriterGrantPostIssueError, "returned token revoked"):
                refresh.mint(refresh.WRITER_ROLE)
        revoke.assert_called_once_with(ISSUED)

    def test_nonzero_exit_with_unconfirmed_provider_revocation_is_hard_failure(self):
        response = types.SimpleNamespace(returncode=1,stdout=json.dumps(grant()),stderr="")
        with patch.object(refresh.subprocess,"run",return_value=response), \
             patch.object(refresh,"revoke_new_writer_token",
                          side_effect=RuntimeError("synthetic provider unavailable")) as revoke:
            with self.assertRaisesRegex(refresh.WriterGrantPostIssueError, "revocation unconfirmed"):
                refresh.mint(refresh.WRITER_ROLE)
        revoke.assert_called_once_with(ISSUED)

    def test_unreadable_issuance_response_never_degrades_to_optional_refusal(self):
        with patch.object(refresh.subprocess,"run",return_value=types.SimpleNamespace(
             returncode=0,stdout="not-json-201",stderr="")):
            with self.assertRaises(refresh.WriterGrantPostIssueError):
                refresh.mint(refresh.WRITER_ROLE)

    def test_timed_out_issuance_never_degrades_to_optional_refusal(self):
        with patch.object(refresh.subprocess,"run",
                          side_effect=TimeoutError("synthetic post-issue transport timeout")):
            with self.assertRaises(refresh.WriterGrantPostIssueError):
                refresh.mint(refresh.WRITER_ROLE)


class PostIssuePersistSafety(unittest.TestCase):
    def run_persist_failure(self, revoke_side_effect=None):
        with tempfile.TemporaryDirectory() as folder:
            parent=Path(folder)/"credentials"
            parent.mkdir(mode=0o700)
            dest=parent/"roles"
            original_fstat=os.fstat
            def trusted(fd):
                st=original_fstat(fd)
                return types.SimpleNamespace(st_mode=st.st_mode, st_uid=0,
                                              st_gid=0, st_nlink=st.st_nlink)
            payload={"token":ISSUED,"expires_at":"2099-01-01T00:00:00Z"}
            revoke=Mock(side_effect=revoke_side_effect)
            cleanup=Mock()
            with patch.object(refresh,"DEST",dest), \
                 patch.object(refresh.os,"geteuid",return_value=0), \
                 patch.object(refresh.os,"fstat",side_effect=trusted), \
                 patch.object(refresh,"selected_roles",return_value=[refresh.WRITER_ROLE]), \
                 patch.object(refresh,"mint",return_value=payload), \
                 patch.object(refresh,"write_token",
                              side_effect=OSError("synthetic disk-full after mint")), \
                 patch.object(refresh,"revoke_new_writer_token",revoke), \
                 patch.object(refresh,"cleanup_failed_writer",cleanup):
                with self.assertRaises(refresh.WriterGrantPostIssueError):
                    refresh.main()
            revoke.assert_called_once_with(ISSUED)
            cleanup.assert_called_once_with()

    def test_write_failure_revokes_issued_token_not_just_old_source(self):
        self.run_persist_failure()

    def test_write_failure_provider_revoke_503_never_reports_success(self):
        self.run_persist_failure(RuntimeError("synthetic HTTP 503"))


if __name__=="__main__":
    unittest.main()
