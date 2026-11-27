#!/usr/bin/env python3
"""Full-refresh failure must not preserve privileged GitHub Ops writer grants."""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import runpy

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "refresh_writer_failclosed", HERE / "multica-zar-github-app-refresh.py")
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


class FullRefreshFailClosed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.parent = root / "credential-store"
        self.parent.mkdir(mode=0o700)
        self.roles = self.parent / "roles"
        self.roles.mkdir(mode=0o700)
        self.source = self.roles / "github-ops-writer.json"
        self.projected = root / "writer-system.json"
        self.runtime = root / "writer-volume.json"
        self.original_fstat = os.fstat

    def create_stale(self):
        for f in (self.source, self.projected, self.runtime):
            f.write_text('{"synthetic":"not-a-real-token"}')
            f.chmod(0o600 if f == self.source else 0o640)

    def run_injected(self, failed_role, *, fail_projection=False):
        def root_fstat(fd):
            st = self.original_fstat(fd)
            return type("Stat", (), {"st_mode":st.st_mode, "st_uid":0,
                                    "st_gid":0, "st_nlink":st.st_nlink})()
        def mint(role):
            if role == failed_role:
                raise RuntimeError("synthetic role failure")
            return {"expires_at":"2099-01-01T00:00:00Z"}
        def write(role, _payload):
            if role == refresh.WRITER_ROLE:
                self.source.write_text('{"synthetic":"replacement-not-a-token"}')
                self.source.chmod(0o600)
        def retire_target(path):
            if path == self.projected and fail_projection:
                raise RuntimeError("synthetic projection ACL refusal")
            if path.is_symlink():
                raise RuntimeError("untrusted projection symlink")
            if path.exists():
                path.unlink()
        def loader(_):
            return {"WRITER_TARGET":self.projected,
                    "WRITER_RUNTIME":self.runtime,
                    "retire_writer_target":retire_target}
        with patch.object(refresh, "DEST", self.roles), \
             patch.object(refresh.os,"geteuid",return_value=0), \
             patch.object(refresh.os,"fstat",side_effect=root_fstat), \
             patch.object(refresh,"mint",side_effect=mint), \
             patch.object(refresh,"write_token",side_effect=write), \
             patch.object(runpy,"run_path",side_effect=loader), \
             patch.dict(os.environ,{refresh.WRITER_OPT_IN:"true"}):
            with self.assertRaisesRegex(RuntimeError,
                  "writer cleanup incomplete" if fail_projection else "synthetic role failure"):
                refresh.main()

    def test_early_nonwriter_failure_revokes_existing_grants(self):
        self.create_stale()
        self.run_injected("github-ops-reader")
        self.assertFalse(self.source.exists())
        self.assertFalse(self.projected.exists())
        self.assertFalse(self.runtime.exists())

    def test_late_nonwriter_failure_revokes_new_writer_and_existing_grants(self):
        self.create_stale()
        self.run_injected("reviewer-product")
        self.assertFalse(self.source.exists())
        self.assertFalse(self.projected.exists())
        self.assertFalse(self.runtime.exists())

    def test_failing_one_cleanup_still_attempts_other_targets(self):
        self.create_stale()
        self.run_injected("reviewer-product",fail_projection=True)
        self.assertFalse(self.source.exists())
        self.assertTrue(self.projected.exists())
        self.assertFalse(self.runtime.exists())


if __name__=="__main__":
    unittest.main()
