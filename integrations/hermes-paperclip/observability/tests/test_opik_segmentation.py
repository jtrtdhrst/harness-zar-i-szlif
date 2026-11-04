"""Regression gates for fail-closed Hermes -> Opik trace segmentation."""
import ast
import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "apply_opik_segmentation.py"
spec = importlib.util.spec_from_file_location("opik_segment", SOURCE)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)

class OpikSegmentationTest(unittest.TestCase):
    def test_known_role_only_from_profile_scoped_path(self):
        transformed = patch.transform(
            "import datetime\n\ndef start_root_trace(\n    task_key: str,\n):\n"
            '    metadata = {\n        "source": "hermes",\n    }\n'
            "    # Build the create payload once and keep it:\n"
            '    create_kwargs = {\n        "tags": tags(),\n    }\n'
        )
        tree = ast.parse(transformed)
        # Evaluate only the pure helper definition with standard pathlib dependency.
        helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                      and n.name == "_verified_role_from_plugin_path")
        code = compile(ast.Module(body=[helper], type_ignores=[]), "<helper>", "exec")
        namespace = {"Path": Path, "_KNOWN_OPIK_ROLES": patch.KNOWN_ROLES}
        exec(code, namespace)
        f = namespace["_verified_role_from_plugin_path"]
        self.assertEqual(f("/opt/data/profiles/cpo/plugins/opik/lifecycle.py"), "cpo")
        self.assertEqual(f("/opt/data/profiles/mcp-engineer/plugins/opik/lifecycle.py"), "mcp-engineer")
        self.assertEqual(f("/opt/data/plugins/opik/lifecycle.py"), "")
        self.assertEqual(f("/tmp/profiles/admin/plugins/opik/lifecycle.py"), "")
        self.assertEqual(f("/tmp/profiles/cpo/plugins/not-opik/lifecycle.py"), "")

    def test_idempotence_is_fail_closed(self):
        template = ("import datetime\n\ndef start_root_trace(\n    task_key: str,\n):\n"
                    '    metadata = {\n        "source": "hermes",\n    }\n'
                    "    # Build the create payload once and keep it:\n"
                    '    create_kwargs = {\n        "tags": tags(),\n    }\n')
        once = patch.transform(template)
        self.assertIn('"agent_role"', once)
        self.assertIn('"memory_bank"', once)
        with self.assertRaisesRegex(ValueError, "anchor drift"):
            patch.transform(once)

    def test_sha_pin_rejects_drift_without_write(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "lifecycle.py"
            file.write_text("suspicious drift\n")
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                patch.prepare(file)
            self.assertEqual(file.read_text(), "suspicious drift\n")

    def test_no_secret_or_prompt_scraping(self):
        template = ("import datetime\n\ndef start_root_trace(\n    task_key: str,\n):\n"
                    '    metadata = {\n        "source": "hermes",\n    }\n'
                    "    # Build the create payload once and keep it:\n"
                    '    create_kwargs = {\n        "tags": tags(),\n    }\n')
        code = patch.transform(template)
        for forbidden in ("bearer", "token", "password", "api_key"):
            self.assertNotIn(forbidden, code.lower())

if __name__ == "__main__":
    unittest.main()
