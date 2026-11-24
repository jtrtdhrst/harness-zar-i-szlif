#!/usr/bin/env python3
"""Regression tests for versioned volume compatibility rollout (KOMAA-1599)."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

if len(sys.argv) < 2:
    raise SystemExit("Provide the pinned upstream nodes.py path or repository root")
PIN = Path(sys.argv[1]).resolve()
if PIN.is_dir():
    PIN /= "codex_provider/nodes.py"
EXPECTED_PIN = "07fb23a93a30c2197953df4811853b7d0a9d7b08fe812347fd58ec89696fee7c"
SPEC = importlib.util.spec_from_file_location(
    "arkcodex_image_compat", Path(__file__).resolve().parents[1] / "patches/arkcodex_image_compat.py"
)
compat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compat)

class CompatibilityRolloutTest(unittest.TestCase):
    def setUp(self):
        source = PIN.read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), EXPECTED_PIN)
        upstream = source.decode("utf-8")
        self.assertEqual(upstream.count('IMAGE_MODEL = "gpt-image-2"'), 1)
        live = upstream.replace(
            'IMAGE_MODEL = "gpt-image-2"', 'IMAGE_MODEL = "gpt-image-2.5"', 1
        ).replace("\n", "\r\n").encode("utf-8")
        self.assertEqual(compat.sha(live), compat.EXPECTED_ORIGINAL_SHA)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "custom" / "nodes.py"
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(live)
        self.backup = Path(self.temp.name) / "user" / "nodes.py.original"
        self.live = live

    def test_install_is_idempotent_and_rollback_restores_exact_bytes(self):
        self.assertEqual(compat.execute(self.target, self.backup, "check"), "PATCHABLE")
        self.assertEqual(compat.execute(self.target, self.backup, "apply"), "PATCHED")
        self.assertTrue(self.backup.is_file())
        self.assertEqual(self.backup.read_bytes(), self.live)
        patched = self.target.read_bytes()
        self.assertNotEqual(patched, self.live)
        self.assertNotIn(b"HOST_EFFORT", patched)
        self.assertIn(b'IMAGE_MODEL = "gpt-image-2.5"', patched)
        self.assertEqual(compat.execute(self.target, self.backup, "apply"), "ALREADY_PATCHED")
        self.assertEqual(self.target.read_bytes(), patched)
        self.assertEqual(compat.execute(self.target, self.backup, "rollback"), "ROLLED_BACK")
        self.assertEqual(self.target.read_bytes(), self.live)
        self.assertEqual(compat.execute(self.target, self.backup, "rollback"), "ALREADY_ORIGINAL")

    def test_unknown_version_denied_with_no_mutation(self):
        bad = self.live.replace(b"INSTRUCTIONS =", b"UNEXPECTED =")
        self.target.write_bytes(bad)
        with self.assertRaises(ValueError):
            compat.execute(self.target, self.backup, "apply")
        self.assertEqual(self.target.read_bytes(), bad)
        self.assertFalse(self.backup.exists())

    def test_symlink_target_denied(self):
        real = self.target.with_suffix(".real")
        self.target.rename(real)
        self.target.symlink_to(real)
        with self.assertRaises(ValueError):
            compat.execute(self.target, self.backup, "apply")
        self.assertEqual(real.read_bytes(), self.live)

    def test_corrupt_backup_denied_with_no_mutation(self):
        self.backup.parent.mkdir()
        self.backup.write_bytes(b"unexpected backup")
        with self.assertRaises(ValueError):
            compat.execute(self.target, self.backup, "apply")
        self.assertEqual(self.target.read_bytes(), self.live)

    def test_check_is_read_only(self):
        self.assertEqual(compat.execute(self.target, self.backup, "check"), "PATCHABLE")
        self.assertEqual(self.target.read_bytes(), self.live)
        self.assertFalse(self.backup.exists())

if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
