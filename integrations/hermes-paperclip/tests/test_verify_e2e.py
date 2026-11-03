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
            "paperclip_issue_id": "KOMAA-1512",
            "executing_agent_id": "executor",
            "paperclip_trace_id": "paperclip-trace-123",
            "hermes_run_id": "hermes-run-123",
            "named_profile": "cho",
            "secrets_exposed": False,
            "profile_auth_test": {"passed": True, "wrong_profile_rejected": True, "dedicated_key_stored_as_secret_ref": True},
            "run_scoped_mcp_bridge": {
                "passed": True,
                "paperclip_token_bound_to_run": True,
                "agent_id_verified": True,
                "wrong_run_rejected": True,
                "wrong_agent_rejected": True,
                "missing_credential_rejected": True,
                "revoked_on_completion": True,
                "secret_not_logged_or_prompted": True,
            },
            "wiki_tool_call": {"passed": True, "paperclip_agent_run_context": True, "actual_content_read": True, "http_status": 200, "invocation_id": "invocation-123"},
            "published_skill": {"passed": True, "version_verified": True, "version_id": "skill-v1"},
            "hindsight": {"passed": True, "later_session_recalled": True, "cross_bank_isolation": True},
            "opik_trace": {
                "passed": True,
                "run_id_correlated": True,
                "model_and_usage_spans": True,
                "trace_id": "trace-123",
                "paperclip_run_id": run,
                "paperclip_issue_id": "KOMAA-1512",
                "paperclip_agent_id": "executor",
                "paperclip_trace_id": "paperclip-trace-123",
                "hermes_run_id": "hermes-run-123",
            },
            "failed_early_auth": {
                "rejected": True,
                "http_status": 401,
                "attempt_id": "negative-attempt-456",
                "acceptance_suite_id": "suite-123",
                "opik_trace_id": "failed-auth-trace-123",
                "paperclip_issue_id": "KOMAA-1512",
                "paperclip_agent_id": "executor",
                "hermes_run_id": None,
            },
            "authoritative_readbacks": {},
            "release": {"passed": True, "sha_verified": True, "rollback_tested": True, "immutable_digest_or_sha": "sha256:abc"},
            "review": {"passed": True, "independent_reviewer": True, "approved": True, "reviewer_agent_id": "reviewer"},
        }

    def test_valid_fully_evidenced_record(self):
        self.assertIn("offline verifier cannot retrieve/authenticate source records; acceptance remains UNVERIFIED", module.validate(self.good(), "cho"))

    def test_accepts_explicit_non_test_profile(self):
        self.assertNotIn("named_profile does not match --expected-profile", module.validate(self.good(), "cho"))

    def test_rejects_retired_profile_even_when_expected_is_same(self):
        d = self.good()
        d["named_profile"] = "hermes-test"
        errors = module.validate(d, "hermes-test")
        self.assertTrue(any("real named Hermes profiles" in e for e in errors))
        self.assertTrue(any("registered real agent profile" in e for e in errors))

    def test_rejects_bank_id_instead_of_profile(self):
        d = self.good()
        d["named_profile"] = "hermes-cho"
        errors = module.validate(d, "cho")
        self.assertTrue(any("registered real agent profile" in e for e in errors))

    def test_blocks_wrong_expected_profile(self):
        self.assertTrue(any("--expected-profile" in e for e in module.validate(self.good(), "ceo")))

    def test_blocks_unverified_tool_execution(self):
        d = self.good()
        d["wiki_tool_call"]["http_status"] = 401
        self.assertTrue(any("http_status" in s for s in module.validate(d, "cho")))

    def test_blocks_wrong_profile(self):
        d = self.good()
        d["named_profile"] = "default"
        self.assertTrue(any("named_profile" in s for s in module.validate(d, "cho")))

    def test_blocks_cross_run_opik_trace(self):
        d = self.good()
        d["opik_trace"]["paperclip_run_id"] = "other"
        self.assertTrue(any("mismatch" in s for s in module.validate(d, "cho")))

    def test_blocks_cross_issue_and_cross_agent_opik_traces(self):
        d = self.good()
        d["opik_trace"]["paperclip_issue_id"] = "KOMAA-OTHER"
        d["opik_trace"]["paperclip_agent_id"] = "other-agent"
        errors = module.validate(d, "cho")
        self.assertIn("opik_trace.paperclip_issue_id mismatch", errors)
        self.assertIn("opik_trace.paperclip_agent_id mismatch", errors)

    def test_blocks_unrevoked_or_misbound_run_credentials(self):
        d = self.good()
        bridge = d["run_scoped_mcp_bridge"]
        bridge["wrong_run_rejected"] = False
        bridge["revoked_on_completion"] = False
        errors = module.validate(d, "cho")
        self.assertIn("run_scoped_mcp_bridge.wrong_run_rejected: not verified", errors)
        self.assertIn("run_scoped_mcp_bridge.revoked_on_completion: not verified", errors)

    def test_accepts_separate_early_auth_attempt_without_hermes_run(self):
        d = self.good()
        self.assertNotIn("failed_early_auth.attempt_id must identify a separate negative attempt", module.validate(d, "cho"))

    def test_blocks_failed_auth_reusing_successful_run_id(self):
        d = self.good()
        d["failed_early_auth"]["attempt_id"] = d["paperclip_run_id"]
        self.assertIn("failed_early_auth.attempt_id must identify a separate negative attempt", module.validate(d, "cho"))

    def test_blocks_auth_denial_after_run_admission(self):
        d = self.good()
        d["failed_early_auth"]["hermes_run_id"] = "unexpected-hermes-run"
        self.assertIn("failed_early_auth.hermes_run_id must be absent before run admission", module.validate(d, "cho"))

    def test_static_evidence_never_claims_authoritative_acceptance(self):
        self.assertIn("offline verifier cannot retrieve/authenticate source records; acceptance remains UNVERIFIED", module.validate(self.good(), "cho"))

    def test_blocks_self_review(self):
        d = self.good()
        d["review"]["reviewer_agent_id"] = "executor"
        self.assertTrue(any("independent" in s for s in module.validate(d, "cho")))

    def test_blocks_missing_fields(self):
        self.assertTrue(module.validate({}, "cho"))

    def test_blocks_unstated_secret_state(self):
        d = self.good()
        d.pop("secrets_exposed")
        self.assertTrue(any("secrets_exposed" in s for s in module.validate(d, "cho")))


if __name__ == "__main__":
    unittest.main()
