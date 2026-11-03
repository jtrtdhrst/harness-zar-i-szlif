import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

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

    def test_service_and_source_are_hard_scoped(self):
        self.assertEqual(m.REPO, "miloszspyrka-code/harness-zar-i-szlif")
        self.assertEqual(m.SERVICE,"paperclip-mcp")
        self.assertEqual(m.IMAGE,"paperclip-mcp:gitops-active")
        self.assertNotIn("app-", m.SERVICE)
        self.assertEqual(m.BASE,"ghcr.io/paperclipai/paperclip:2026.1023.0")

if __name__=="__main__":
    unittest.main()
