#!/usr/bin/env python3
"""Synthetic-only tests for read-only GitHub Ops runtime provenance preflight."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).with_name("github-ops-runtime-preflight.py")
spec = importlib.util.spec_from_file_location("github_ops_runtime_preflight", SOURCE)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class RuntimePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.installed = self.root / "installed"
        self.source.mkdir()
        self.installed.mkdir()
        for name in preflight.FILES:
            (self.source / name).write_text("nonsecret-synthetic-source")
            (self.installed / name).write_text("nonsecret-synthetic-source")
        self.role = self.root / "role.json"
        self.projection = self.root / "projection.json"
        self.volume = self.root / "volume.json"

    def check(self):
        return preflight.evaluate(self.source, self.installed, self.role, self.projection, self.volume)

    def test_matching_scripts_report_parity_not_release_authorization(self):
        result = self.check()
        self.assertTrue(result["runtime_source_current"])
        self.assertFalse(result["writer_files_present"])
        self.assertTrue(all(value == "MATCH" for value in result["source"].values()))
        self.assertIn("do not authorize writes", result["note"])

    def test_outdated_refresher_is_a_hard_source_mismatch(self):
        (self.installed / preflight.FILES[0]).write_text("stale-script")
        result = self.check()
        self.assertFalse(result["runtime_source_current"])
        self.assertEqual(result["source"][preflight.FILES[0]], "DRIFT")

    def test_symlinked_runtime_source_is_untrusted(self):
        file = self.installed / preflight.FILES[1]
        file.unlink()
        file.symlink_to(self.source / preflight.FILES[1])
        result = self.check()
        self.assertEqual(result["source"][preflight.FILES[1]], "UNTRUSTED")

    def test_writer_files_are_stat_only_and_never_printed(self):
        self.role.write_text("secret-not-for-output")
        self.projection.write_text("secret-not-for-output")
        self.volume.write_text("secret-not-for-output")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = preflight.main([
                "--source-dir", str(self.source), "--installed-dir", str(self.installed),
                "--writer-role-path", str(self.role),
                "--writer-projection-path", str(self.projection),
                "--writer-volume-path", str(self.volume),
                "--require-writer"
            ])
        self.assertNotIn("secret-not-for-output", out.getvalue())
        # Read-only test users cannot create trusted root-owned writer files.
        if not preflight.evaluate(self.source, self.installed, self.role, self.projection, self.volume)["writer_files_present"]:
            self.assertEqual(status, 3)

    def test_cli_returns_error_on_source_drift_even_without_writer_request(self):
        (self.installed / preflight.FILES[1]).write_text("old version")
        result = io.StringIO()
        with contextlib.redirect_stdout(result):
            status = preflight.main([
                "--source-dir", str(self.source), "--installed-dir", str(self.installed),
                "--writer-role-path", str(self.role),
                "--writer-projection-path", str(self.projection),
                "--writer-volume-path", str(self.volume)
            ])
        self.assertEqual(status, 2)
        self.assertIn("DRIFT", result.getvalue())


if __name__ == "__main__":
    unittest.main()
