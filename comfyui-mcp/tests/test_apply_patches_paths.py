"""Fail-closed ComfyUI volume restore helper: no half-apply on missing source."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RestorePatchPathsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "patches").mkdir()
        (self.root / "canvas-bridge").mkdir()
        (self.root / "bin").mkdir()
        shutil.copyfile(ROOT / "patches/apply.sh", self.root / "patches/apply.sh")
        for filename in ("qc_reject_patch.py", "llm_json_tolerant_patch.py"):
            (self.root / "patches" / filename).write_text("# fixture\n")
        for filename in ("__init__.py", "comfy_bridge.py"):
            (self.root / "canvas-bridge" / filename).write_text("# fixture\n")
        self.calls = self.root / "calls.log"
        helper = self.root / "bin/sudo"
        helper.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$MOCK_DOCKER_CALLS"\nexit 0\n')
        helper.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.root / 'bin'}:{os.environ['PATH']}",
                        MOCK_DOCKER_CALLS=str(self.calls), COMFY_CTN="test-comfy-container")

    def run_script(self):
        return subprocess.run(["bash", str(self.root / "patches/apply.sh")],
                              env=self.env, capture_output=True, text=True, timeout=8)

    def test_all_sources_referenced_from_correct_directory(self):
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stderr)
        calls = self.calls.read_text()
        for filename in ("__init__.py", "comfy_bridge.py"):
            self.assertIn(str(self.root / "canvas-bridge" / filename), calls)
        self.assertIn("docker inspect test-comfy-container", calls)
        self.assertIn("/app/custom_nodes/comfyui-arkennemasis/mcp_service/", calls)

    def test_missing_bridge_file_refuses_before_container_mutation(self):
        (self.root / "canvas-bridge/comfy_bridge.py").unlink()
        out = self.run_script()
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("Missing source:", out.stderr)
        self.assertFalse(self.calls.exists(), "No docker calls allowed on preflight failure")

    def test_missing_patch_refuses_before_container_mutation(self):
        (self.root / "patches/qc_reject_patch.py").unlink()
        out = self.run_script()
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("Missing source:", out.stderr)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
