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

    def test_merged_pr_with_successful_ci_does_not_need_fake_github_reviewer(self):
        payload={
            "verified":True,"pr":25,"head_sha":"a"*40,"checks_http":200,
            "checks":[{"name":"validate-paperclip-mcp","status":"completed","conclusion":"success"}],
            "checks_total":1,
        }
        self.assertEqual(m.assess_release_attestation(payload),25)
        for invalid in [
            {**payload,"verified":False},
            {**payload,"pr":0},
            {**payload,"head_sha":"main"},
            {**payload,"checks_http":403},
            {**payload,"checks":[],"checks_total":0},
            {**payload,"checks_total":101},
            {**payload,"checks_total":2},
            {**payload,"checks":[{"name":"validate-paperclip-mcp","status":"in_progress","conclusion":None}]},
            {**payload,"checks":[{"name":"validate-paperclip-mcp","status":"completed","conclusion":"failure"}]},
            {**payload,"checks":[{"name":"some-unrelated-check","status":"completed","conclusion":"success"}]},
            {**payload,"checks":[{"name":"validate-paperclip-mcp","status":"completed","conclusion":"success"},{"name":"validate-paperclip-mcp","status":"completed","conclusion":"success"}],"checks_total":2},
            {**payload,"checks":[{"name":"validate-paperclip-mcp","status":"completed","conclusion":"success"},{"name":"other","status":"completed","conclusion":"failure"}],"checks_total":2},
        ]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(RuntimeError):
                    m.assess_release_attestation(invalid)

    def test_native_result_requires_first_class_identity_and_exact_sha(self):
        valid={"verified":True,"repository":m.REPO,"pr":25,"head_sha":"a"*40,
               "merge_sha":"b"*40, **{k:"12345678-1234-4234-8234-123456789abc"
               for k in ("issue_id","decision_id","reviewer_agent_id","source_run_id")}}
        self.assertIn("decision_id",m.validate_native_review_result(valid,25,"a"*40,"b"*40))
        for changed in ({"verified":False},{"repository":"other/repo"},{"pr":26},
                        {"head_sha":"c"*40},{"merge_sha":"d"*40},{"decision_id":None},
                        {"source_run_id":"not-a-uuid"},{"reviewer_agent_id":None}):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(RuntimeError,"identity/SHA mismatch"):
                    m.validate_native_review_result({**valid,**changed},25,"a"*40,"b"*40)

    def test_native_verifier_executes_only_root_owned_fixed_script(self):
        valid={"verified":True,"repository":m.REPO,"pr":25,"head_sha":"a"*40,
               "merge_sha":"b"*40, **{k:"12345678-1234-4234-8234-123456789abc"
               for k in ("issue_id","decision_id","reviewer_agent_id","source_run_id")}}
        from unittest.mock import MagicMock
        good=MagicMock()
        good.lstat.return_value=SimpleNamespace(st_mode=0o100755,st_uid=0)
        good.__str__.return_value="/usr/local/libexec/paperclip_native_release_gate.py"
        with patch.object(m,"NATIVE_GATE",good),patch.object(m,"run",return_value=SimpleNamespace(returncode=0,stdout=json.dumps(valid))) as call:
            m.verify_native_review(25,"a"*40,"b"*40)
            args=call.call_args.args[0]
            self.assertIn("--merge-sha",args)
            self.assertNotIn("--issue-id",args)
            self.assertNotIn("--review-approved",args)
        with patch.object(m,"NATIVE_GATE",good),patch.object(m,"run",return_value=SimpleNamespace(returncode=1,stdout=json.dumps(valid))):
            with self.assertRaisesRegex(RuntimeError,"independent review denied"):
                m.verify_native_review(25,"a"*40,"b"*40)
        for mode,uid in ((0o120777,0),(0o100777,0),(0o100755,1000)):
            good.lstat.return_value=SimpleNamespace(st_mode=mode,st_uid=uid)
            with patch.object(m,"NATIVE_GATE",good), self.assertRaisesRegex(RuntimeError,"ownership/mode invalid"):
                m.verify_native_review(25,"a"*40,"b"*40)
        good.lstat.side_effect=FileNotFoundError()
        with patch.object(m,"NATIVE_GATE",good), self.assertRaisesRegex(RuntimeError,"not installed"):
            m.verify_native_review(25,"a"*40,"b"*40)

    def test_all_mcp_merges_need_independent_exact_sha_approval(self):
        first="1"*40; second="2"*40; previous="0"*40
        def fake_docker(*a,**kw):
            if "rev-list" in a:return first+"\n"+second
            if "show" in a:return previous+" "+("9"*40)
            if "diff" in a:return ("paperclip-mcp/src/safe.ts" if a[-1]==first else "docs/README.md")
            raise AssertionError(a)
        with patch.object(m,"docker_core",side_effect=fake_docker),patch.object(m,"verified_pr",return_value={"number":25,"head_sha":"a"*40}) as gh,patch.object(m,"verify_native_review",return_value={"decision_id":"x"}) as native:
            got=m.verify_reviewed_history("/repo",previous,second)
        self.assertEqual(len(got),1)
        self.assertEqual(got[0]["merge_sha"],first)
        gh.assert_called_once_with(first)
        native.assert_called_once_with(25,"a"*40,first)
        with patch.object(m,"docker_core",side_effect=lambda *a,**kw: ("1"*40 if "rev-list" in a else previous)):
            with self.assertRaises(RuntimeError):
                m.verify_reviewed_history("/repo",previous,first)
        with self.assertRaisesRegex(RuntimeError,"Missing immutable prior"):
            m.verify_reviewed_history("/repo",None,second)

    def test_service_and_source_are_hard_scoped(self):
        self.assertEqual(m.REPO, "miloszspyrka-code/harness-zar-i-szlif")
        self.assertEqual(m.SERVICE,"paperclip-mcp")
        self.assertEqual(m.IMAGE,"paperclip-mcp:gitops-active")
        self.assertNotIn("app-", m.SERVICE)
        self.assertEqual(m.BASE,"ghcr.io/paperclipai/paperclip:2026.1023.0")

if __name__=="__main__":
    unittest.main()
