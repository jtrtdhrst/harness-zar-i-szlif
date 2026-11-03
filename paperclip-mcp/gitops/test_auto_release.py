import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location("paperclip_mcp_auto_release", Path(__file__).with_name("paperclip-mcp-auto-release.py"))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ReleaseSafetyTests(unittest.TestCase):
    def test_only_component_code_changes_trigger_mcp_deploy(self):
        allowed=[
            "paperclip-mcp/Dockerfile",
            "paperclip-mcp/entrypoint.sh",
            "paperclip-mcp/src/workspace-native.ts",
            "paperclip-mcp/mcp-gateway/gateway.mjs",
            "paperclip-mcp/plugin-runtime/build.mjs",
            "paperclip-mcp/plugin-skills/README.md",
        ]
        for name in allowed:
            with self.subTest(path=name):
                self.assertTrue(m.is_component_change(name))
        disallowed=[
            "paperclip-mcp/docs/readme.md",
            "paperclip-mcp/gitops/paperclip-mcp-auto-release.py",
            "plasmic-mcp/src/server.ts",
            "comfyui-mcp/server.py",
            "paperclip-mcp/srcx/not-native.ts",
            "paperclip-mcp/Dockerfile.modified",
            "mcp-edge/Dockerfile",
        ]
        for name in disallowed:
            with self.subTest(path=name):
                self.assertFalse(m.is_component_change(name))

    def test_only_exact_40_hex_sha_is_accepted(self):
        self.assertTrue(m.validate_sha("a" * 40))
        for sha in ["main", "a"*39, "A"*40, "a"*40 + ";rm -rf /", None, "", "refs/heads/main"]:
            self.assertFalse(m.validate_sha(sha))

    def test_git_state_fails_closed_on_wrong_sha(self):
        with tempfile.TemporaryDirectory() as root:
            previous=m.STATE
            try:
                m.STATE=Path(root)/"state.json"
                m.STATE.write_text(json.dumps({"last_checked_sha":"not-a-commit"}))
                with self.assertRaisesRegex(RuntimeError,"SHA invalid"):
                    m.read_state()
            finally:
                m.STATE=previous

    def test_release_pr_verification_never_takes_unvalidated_input(self):
        with self.assertRaisesRegex(RuntimeError,"Invalid merge SHA"):
            m.verified_pr('main; echo unsafe')

    def test_candidate_build_sends_tar_bytes_not_file_object(self):
        with tempfile.TemporaryDirectory() as root:
            archive=Path(root)/"source.tar.gz"
            archive.write_bytes(b"fake-test-tar-context")
            invoked=[]
            def fake_run(argv, timeout=100, stdin=None, allow_fail=False):
                invoked.append((argv, stdin))
                if argv[1] == "build":
                    self.assertIsInstance(stdin, bytes)
                    self.assertEqual(stdin, b"fake-test-tar-context")
                    return SimpleNamespace(stdout=b"", stderr=b"", returncode=0)
                if argv[1:3] == ["image", "inspect"]:
                    return SimpleNamespace(stdout="sha256:" + "c"*64 + chr(10), stderr="", returncode=0)
                raise AssertionError("Unexpected command")
            with patch.object(m, "run", side_effect=fake_run), patch.object(m, "ensure_candidate_tests"):
                tag, image_id=m.build_image("a"*40, str(archive))
            self.assertEqual(tag, "paperclip-mcp:gitops-" + "a"*40)
            self.assertEqual(image_id, "sha256:" + "c"*64)
            self.assertEqual(len(invoked), 2)

    def test_actual_public_mcp_denial_probe_requires_401(self):
        with patch.object(m, "run", return_value=SimpleNamespace(stdout="401", returncode=0)):
            m.verify_anonymous_mcp_denial()
        for code in ["200", "403", "404", "500", "", "301"]:
            with self.subTest(status=code):
                with patch.object(m, "run", return_value=SimpleNamespace(stdout=code, returncode=0)):
                    with self.assertRaisesRegex(RuntimeError, "must return 401"):
                        m.verify_anonymous_mcp_denial()

    def test_service_and_source_are_hard_scoped(self):
        self.assertEqual(m.REPO, "miloszspyrka-code/harness-zar-i-szlif")
        self.assertEqual(m.SERVICE,"paperclip-mcp")
        self.assertEqual(m.IMAGE,"paperclip-mcp:gitops-active")
        self.assertNotIn("app-", m.SERVICE)
        self.assertEqual(m.BASE,"ghcr.io/paperclipai/paperclip:2026.1023.0")

if __name__=="__main__":
    unittest.main()
