import ast
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "arkennemasis-image-reasoning.patch"
UPSTREAM_COMMIT = "9fea8c02d6937189f31fab4bf85744e8e38a39c5"
UPSTREAM_NODES_SHA256 = "07fb23a93a30c2197953df4811853b7d0a9d7b08fe812347fd58ec89696fee7c"


class ImageReasoningPatchTest(unittest.TestCase):
    def test_patch_removes_effort_from_image_wire_payload_only(self):
        source = Path(sys.argv[1]).resolve()
        commit = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
        ).strip()
        self.assertEqual(commit, UPSTREAM_COMMIT)
        nodes = source / "codex_provider" / "nodes.py"
        self.assertEqual(hashlib.sha256(nodes.read_bytes()).hexdigest(), UPSTREAM_NODES_SHA256)

        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "codex_provider" / "nodes.py"
            target.parent.mkdir()
            shutil.copyfile(nodes, target)
            subprocess.run(["git", "apply", str(PATCH)], cwd=temp, check=True)

            tree = ast.parse(target.read_text())
            image_model = next(
                node.value.value for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                and any(isinstance(name, ast.Name) and name.id == "IMAGE_MODEL" for name in node.targets)
                and isinstance(node.value, ast.Constant)
            )
            self.assertEqual(image_model, "gpt-image-2.5")
            blocking = next(
                node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "_blocking"
            )
            payload = next(
                node.value for node in ast.walk(blocking)
                if isinstance(node, ast.Assign)
                and any(isinstance(name, ast.Name) and name.id == "payload" for name in node.targets)
            )
            self.assertIsInstance(payload, ast.Dict)
            keys = {key.value for key in payload.keys if isinstance(key, ast.Constant)}
            self.assertIn("tools", keys)
            self.assertNotIn("reasoning", keys)
            self.assertNotIn("HOST_EFFORT", ast.unparse(tree))


if __name__ == "__main__":
    unittest.main(argv=[__file__])
