#!/usr/bin/env python3
"""Guard exact BGH GitHub App reader/writer role parity without exposing tokens."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent

def load(stem, name):
    spec = importlib.util.spec_from_file_location(name, HERE / stem)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class ProjectionScope(unittest.TestCase):
    def test_reader_projection_matches_minter(self):
        mint = load("multica-zar-github-app-refresh.py", "bgh_minter_reader")
        project = load("github-ops-token-project.py", "bgh_projector_reader")
        self.assertEqual(project.PERMISSIONS, mint.ROLE_PERMISSIONS["github-ops-reader"])
        self.assertEqual(project.ROLE, "github-ops-reader")
        self.assertEqual(project.REPOS, set(mint.REPOS))

    def test_writer_projection_matches_minter_exactly(self):
        mint = load("multica-zar-github-app-refresh.py", "bgh_minter_writer")
        project = load("github-ops-token-project.py", "bgh_projector_writer")
        expected = {"actions":"write", "contents":"write", "pull_requests":"write", "metadata":"read"}
        self.assertEqual(project.WRITER_PERMISSIONS, expected)
        self.assertEqual(project.WRITER_PERMISSIONS, mint.ROLE_PERMISSIONS["github-ops-writer"])
        self.assertEqual(project.WRITER_ROLE, "github-ops-writer")
        self.assertEqual(project.REPOS, set(mint.REPOS))


class WriterRevocation(unittest.TestCase):
    def test_absent_writer_does_not_create_a_credential(self):
        import tempfile
        from unittest.mock import patch
        project = load("github-ops-token-project.py", "bgh_projector_absent")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'writer.json'
            with patch.object(project, 'WRITER_TARGET', target):
                self.assertFalse(project.retire_writer_target())
                self.assertFalse(target.exists())

    def test_stale_writer_is_removed_only_for_exact_safe_identity(self):
        import tempfile
        import stat
        from types import SimpleNamespace
        from unittest.mock import patch
        project = load("github-ops-token-project.py", "bgh_projector_safe")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'writer.json'
            target.write_text('synthetic-marker')
            target.chmod(0o640)
            existing = target.lstat()
            trusted = SimpleNamespace(st_mode=existing.st_mode, st_uid=0,
                st_gid=project.NODE_GID, st_nlink=1)
            with patch.object(project, 'WRITER_TARGET', target), patch.object(project.os, 'lstat', return_value=trusted):
                self.assertTrue(project.retire_writer_target())
            self.assertFalse(target.exists())

    def test_untrusted_projected_writer_is_never_deleted(self):
        import tempfile
        from unittest.mock import patch
        project = load("github-ops-token-project.py", "bgh_projector_untrusted")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'writer.json'
            target.write_text('unchanged')
            target.chmod(0o644)
            with patch.object(project, 'WRITER_TARGET', target):
                with self.assertRaisesRegex(RuntimeError, 'Untrusted projected writer'):
                    project.retire_writer_target()
            self.assertEqual(target.read_text(), 'unchanged')


    def test_reader_failure_uses_shared_provider_first_revocation(self):
        import contextlib
        from unittest.mock import patch, Mock
        project = load("github-ops-token-project.py", "bgh_reader_failure_revoke")
        cleanup = Mock()
        with patch.object(project, "writer_lifecycle_lock", return_value=contextlib.nullcontext()), \
             patch.object(project, "project", side_effect=RuntimeError("reader invalid")), \
             patch.object(project.runpy, "run_path", return_value={"cleanup_failed_writer": cleanup}):
            with self.assertRaisesRegex(RuntimeError, "reader invalid"):
                project.main()
        cleanup.assert_called_once_with()

    def test_writer_projection_failure_reports_provider_revoke_failure(self):
        import contextlib
        import tempfile
        from unittest.mock import patch, Mock
        project = load("github-ops-token-project.py", "bgh_writer_failure_revoke")
        cleanup = Mock(side_effect=RuntimeError("Writer cleanup incomplete"))
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "writer.json"
            source.write_text("synthetic-only")
            with patch.object(project, "WRITER_SOURCE", source), \
                 patch.object(project, "writer_lifecycle_lock", return_value=contextlib.nullcontext()), \
                 patch.object(project, "project", side_effect=["2099-01-01T00:00:00Z",
                                                            RuntimeError("writer invalid")]), \
                 patch.object(project.runpy, "run_path", return_value={"cleanup_failed_writer": cleanup}):
                with self.assertRaisesRegex(RuntimeError, "Writer cleanup incomplete"):
                    project.main()
        cleanup.assert_called_once_with()

    def test_writer_projection_failure_attempts_remote_revocation(self):
        import contextlib
        import tempfile
        from unittest.mock import patch, Mock
        project = load("github-ops-token-project.py", "bgh_writer_failure_revokes")
        cleanup = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "writer.json"
            source.write_text("synthetic-only")
            with patch.object(project, "WRITER_SOURCE", source), \
                 patch.object(project, "writer_lifecycle_lock", return_value=contextlib.nullcontext()), \
                 patch.object(project, "project", side_effect=["2099-01-01T00:00:00Z",
                                                            RuntimeError("writer invalid")]), \
                 patch.object(project.runpy, "run_path", return_value={"cleanup_failed_writer": cleanup}):
                with self.assertRaisesRegex(RuntimeError, "writer invalid"):
                    project.main()
        cleanup.assert_called_once_with()


class RuntimeVolumeProjection(unittest.TestCase):
    def test_scoped_writer_is_atomically_projected_into_existing_volume(self):
        import json
        import os
        import tempfile
        import types
        from unittest.mock import patch
        project = load("github-ops-token-project.py", "bgh_projector_volume")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_dir = root / "volume"
            runtime_dir.mkdir(mode=0o750)
            runtime_dir.chmod(0o750)
            source = root / "writer.json"
            grant = {
                "role": project.WRITER_ROLE, "app_id": 5398752,
                "installation_id": 173456397,
                "permissions": project.WRITER_PERMISSIONS,
                "repositories": sorted(project.REPOS),
                "token": "synthetic-not-production",
            }
            source.write_text(json.dumps(grant))
            source.chmod(0o640)
            final = runtime_dir / "writer.json"
            actual_fstat = os.fstat
            def trusted(fd):
                st = actual_fstat(fd)
                return types.SimpleNamespace(
                    st_mode=st.st_mode, st_uid=0, st_gid=project.NODE_GID,
                    st_nlink=st.st_nlink, st_size=st.st_size
                )
            with patch.object(project, 'WRITER_TARGET', source), \
                 patch.object(project, 'WRITER_RUNTIME', final), \
                 patch.object(project.os, 'fstat', side_effect=trusted), \
                 patch.object(project.os, 'fchown', return_value=None):
                project.project_writer_runtime()
            self.assertEqual(json.loads(final.read_text())["role"], "github-ops-writer")
            self.assertEqual(final.stat().st_mode & 0o777, 0o640)
            self.assertEqual(sorted(p.name for p in runtime_dir.iterdir()), ['writer.json'])

    def test_wrong_scope_never_projects_to_runtime_volume(self):
        import json
        import os
        import tempfile
        import types
        from unittest.mock import patch
        project = load("github-ops-token-project.py", "bgh_projector_wrong_scope")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_dir = root / "volume"
            runtime_dir.mkdir(mode=0o750)
            runtime_dir.chmod(0o750)
            source = root / "writer.json"
            source.write_text(json.dumps({
                "role": "github-ops-writer", "app_id": 5398752,
                "installation_id": 173456397,
                "permissions": {"contents": "write"},
                "repositories": sorted(project.REPOS)
            }))
            source.chmod(0o640)
            final = runtime_dir / "writer.json"
            real_fstat = os.fstat
            def trusted(fd):
                st = real_fstat(fd)
                return types.SimpleNamespace(st_mode=st.st_mode, st_uid=0,
                    st_gid=project.NODE_GID, st_nlink=st.st_nlink, st_size=st.st_size)
            with patch.object(project, 'WRITER_TARGET', source), \
                 patch.object(project, 'WRITER_RUNTIME', final), \
                 patch.object(project.os, 'fstat', side_effect=trusted):
                with self.assertRaisesRegex(RuntimeError, 'scope mismatch'):
                    project.project_writer_runtime()
            self.assertFalse(final.exists())

    def test_stale_runtime_volume_token_revoked_independently(self):
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        project = load("github-ops-token-project.py", "bgh_projector_volume_revoke")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'writer.json'
            target.write_text('synthetic-no-secret')
            target.chmod(0o640)
            st = target.lstat()
            trusted = SimpleNamespace(st_mode=st.st_mode, st_uid=0,
                st_gid=project.NODE_GID, st_nlink=1)
            with patch.object(project.os, 'lstat', return_value=trusted):
                self.assertTrue(project.retire_writer_target(target))
            self.assertFalse(target.exists())

if __name__ == "__main__":
    unittest.main()
