import importlib.util
import pathlib
import unittest

module_path = pathlib.Path(__file__).resolve().parents[1] / "verify_e2e.py"
spec = importlib.util.spec_from_file_location("verify_e2e", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EvidenceGateTests(unittest.TestCase):
    def good(self):
        run = "98838fa8-5a4f-4275-8b30-3692081884f9"
        return {
            "paperclip_run_id": run,
            "executing_agent_id": "executor",
            "named_profile": "cho",
            "secrets_exposed": False,
            "profile_auth_test": {"passed": True, "wrong_profile_rejected": True, "dedicated_key_stored_as_secret_ref": True},
            "wiki_tool_call": {"passed": True, "paperclip_agent_run_context": True, "actual_content_read": True, "http_status": 200, "invocation_id": "invocation-123"},
            "published_skill": {"passed": True, "version_verified": True, "version_id": "skill-v1"},
            "hindsight": {"passed": True, "later_session_recalled": True, "cross_bank_isolation": True},
            "opik_trace": {"passed": True, "run_id_correlated": True, "model_and_usage_spans": True, "trace_id": "trace-123", "paperclip_run_id": run},
            "release": {"passed": True, "sha_verified": True, "rollback_tested": True, "immutable_digest_or_sha": "sha256:abc"},
            "review": {"passed": True, "independent_reviewer": True, "approved": True, "reviewer_agent_id": "reviewer"},
        }

    def test_valid_fully_evidenced_record(self):
        self.assertEqual(module.validate(self.good()), [])

    def test_blocks_unverified_tool_execution(self):
        d = self.good()
        d["wiki_tool_call"]["http_status"] = 401
        self.assertTrue(any("http_status" in s for s in module.validate(d)))

    def test_blocks_wrong_profile(self):
        d = self.good()
        d["named_profile"] = "default"
        self.assertTrue(any("named_profile" in s for s in module.validate(d)))

    def test_blocks_retired_test_profile(self):
        d = self.good()
        d["named_profile"] = "hermes-test"
        self.assertTrue(any("named_profile" in item for item in module.validate(d)))

    def test_blocks_retired_release_profile(self):
        d = self.good()
        d["named_profile"] = "delivery-release-manager"
        self.assertTrue(any("named_profile" in item for item in module.validate(d)))

    def test_accepts_real_cpo_profile(self):
        d = self.good()
        d["named_profile"] = "cpo"
        self.assertEqual(module.validate(d), [])

    def test_blocks_cross_run_opik_trace(self):
        d = self.good()
        d["opik_trace"]["paperclip_run_id"] = "other"
        self.assertTrue(any("mismatch" in s for s in module.validate(d)))

    def test_blocks_self_review(self):
        d = self.good()
        d["review"]["reviewer_agent_id"] = "executor"
        self.assertTrue(any("independent" in s for s in module.validate(d)))

    def test_blocks_missing_fields(self):
        self.assertTrue(module.validate({}))

    def test_blocks_unstated_secret_state(self):
        d = self.good()
        d.pop("secrets_exposed")
        self.assertTrue(any("secrets_exposed" in s for s in module.validate(d)))


if __name__ == "__main__":
    unittest.main()
