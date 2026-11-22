"""Tests for the build-time plugin-loader bound patch (no Docker, no network).

The fixture is a byte-identical copy of ``plugins/plugin_loader.py`` from
``nousresearch/hermes-agent`` v0.22.5 (the image the gateway Dockerfile pins).
Keeping it verbatim is what makes the SHA pin meaningful: if the pin and the
fixture disagree, the build-time patch would anchor on different code.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

GATEWAY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GATEWAY_DIR))

from install_plugin_load_wait import (  # noqa: E402
    DEFAULT_SECS,
    ENV_VAR,
    EXPECTED_SHA256,
    patch_source,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "plugin_loader_v0.22.5.py"
ORIGINAL_SOURCE = FIXTURE.read_text(encoding="utf-8")


def _load_patched(source_text: str):
    """Import the patched loader from a temp file and return the resolved bound."""
    with tempfile.TemporaryDirectory() as tmp:
        mod_path = Path(tmp) / "plugin_loader_probe.py"
        mod_path.write_text(source_text, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("plugin_loader_probe", mod_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["plugin_loader_probe"] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop("plugin_loader_probe", None)
        return module._CONCURRENT_LOAD_WAIT_SECS


class FixturePinTests(unittest.TestCase):
    def test_fixture_matches_pinned_upstream_bytes(self):
        digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(digest, EXPECTED_SHA256)
        self.assertIn("_CONCURRENT_LOAD_WAIT_SECS = 10.0\n", ORIGINAL_SOURCE)


class PatchShapeTests(unittest.TestCase):
    def setUp(self):
        self.patched = patch_source(ORIGINAL_SOURCE)

    def test_hardcoded_bound_is_replaced_by_env_read(self):
        self.assertNotIn("_CONCURRENT_LOAD_WAIT_SECS = 10.0\n", self.patched)
        self.assertIn(f"_env_seconds({ENV_VAR!r}, {DEFAULT_SECS!r})", self.patched)

    def test_patch_adds_only_the_two_missing_stdlib_imports(self):
        self.assertIn("import math\nimport os\n", self.patched)
        self.assertEqual(self.patched.count("import logging\n"), 1)

    def test_patched_source_still_compiles(self):
        compile(self.patched, str(FIXTURE), "exec")


class BoundResolutionTests(unittest.TestCase):
    def setUp(self):
        self.patched = patch_source(ORIGINAL_SOURCE)
        self._saved = os.environ.get(ENV_VAR)
        os.environ.pop(ENV_VAR, None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = self._saved

    def test_default_is_unchanged_when_env_is_unset(self):
        self.assertEqual(_load_patched(self.patched), 10.0)

    def test_operator_override_is_honoured(self):
        os.environ[ENV_VAR] = "45"
        self.assertEqual(_load_patched(self.patched), 45.0)

    def test_surrounding_whitespace_is_tolerated(self):
        os.environ[ENV_VAR] = " 30 "
        self.assertEqual(_load_patched(self.patched), 30.0)

    def test_unusable_values_fall_back_to_the_pinned_default(self):
        for raw in ("abc", "0", "-3", "nan", "inf"):
            with self.subTest(raw=raw):
                os.environ[ENV_VAR] = raw
                self.assertEqual(_load_patched(self.patched), 10.0)


class DriftGuardTests(unittest.TestCase):
    def test_anchor_drift_fails_closed(self):
        drifted = ORIGINAL_SOURCE.replace(
            "_CONCURRENT_LOAD_WAIT_SECS = 10.0\n", "_CONCURRENT_LOAD_WAIT_SECS = 12.0\n"
        )
        with self.assertRaises(RuntimeError):
            patch_source(drifted)

    def test_second_patch_is_refused(self):
        once = patch_source(ORIGINAL_SOURCE)
        with self.assertRaises(RuntimeError):
            patch_source(once)


if __name__ == "__main__":
    unittest.main()
