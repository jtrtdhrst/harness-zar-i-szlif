"""Offline regression tests for existing native Multica release admission gate."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

P = Path(__file__).with_name("multica_native_release_gate.py")
spec = importlib.util.spec_from_file_location("zari213_release_gate", P)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

HEAD = "a" * 40
MERGE = "b" * 40
HE = "c1c8b457-e602-4eda-8ac7-67b994348878"
CTO = "3a54e0b4-6526-4de5-a1fd-e66e205cb3b4"
TASK = "3d21fdf1-44bc-4515-a111-3d5be75e00a9"
HARNESS = "jtrtdhrst/harness-zar-i-szlif"
PRODUCT = "jtrtdhrst/zar-i-szlif"


class RepoAdmissionTests(unittest.TestCase):
    def test_current_owner_repos_admitted(self):
        for repo in (HARNESS, PRODUCT):
            gate.validate_input(repo, 215, HEAD, MERGE, "ZARI-213")

    def test_old_owner_not_implicitly_authorized(self):
        for repo in ("miloszspyrka-code/harness-zar-i-szlif",
                     "miloszspyrka-code/zar-i-szlif",
                     "attacker/harness-zar-i-szlif"):
            with self.subTest(repo=repo), self.assertRaisesRegex(gate.Denied, "invalid_repository_or_pr"):
                gate.validate_input(repo, 215, HEAD, MERGE, "ZARI-213")

    def test_only_release_evidence_comments_are_loaded(self):
        sql = gate.query(HARNESS, 215, "ZARI-213")
        self.assertIn("c.content ILIKE '%RELEASE_APPROVED%'", sql)
        self.assertIn("c.content ILIKE '%CHANGES_REQUESTED%'", sql)
        self.assertIn("c.deleted_at IS NULL", sql)

    def test_stale_or_malformed_sha_denied(self):
        with self.assertRaisesRegex(gate.Denied, "invalid_sha"):
            gate.validate_input(HARNESS, 215, "abc", MERGE, "ZARI-213")

    def test_wrong_issue_ref_denied(self):
        with self.assertRaisesRegex(gate.Denied, "invalid_issue_ref"):
            gate.validate_input(HARNESS, 215, HEAD, MERGE, "213")

    def approval_row(self, *, status="in_review", reviewer=CTO, producer=HE):
        return {
            "issue_id": "01a1e0ac-5d9e-7c46-8add-67be5ff69dcc",
            "issue_number": 213,
            "issue_status": status,
            "producer_id": producer,
            "producer_runs": 1,
            "comments": [{
                "author_type": "agent",
                "author_id": reviewer,
                "content": "RELEASE_APPROVED " + HEAD + "\nPRODUCER " + producer,
                "source_task_id": TASK,
                "created_at": "2026-11-22T15:00:00Z",
            }],
        }

    def test_security_hold_fails_before_approval(self):
        with self.assertRaisesRegex(gate.Denied, "issue_not_reviewable"):
            gate.verify(self.approval_row(status="blocked"), HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_independent_exact_sha_review_can_pass(self):
        with patch.object(gate, "task_record", return_value={"agent_id": CTO, "status": "completed"}):
            outcome = gate.verify(self.approval_row(), HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")
        self.assertTrue(outcome["verified"])
        self.assertEqual(outcome["head_sha"], HEAD)

    def test_self_review_rejected(self):
        with self.assertRaisesRegex(gate.Denied, "not_independent"):
            gate.verify(self.approval_row(producer=CTO), HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_uncompleted_reviewer_task_rejected(self):
        with patch.object(gate, "task_record", return_value={"agent_id": CTO, "status": "running"}):
            with self.assertRaisesRegex(gate.Denied, "reviewer_task_not_completed"):
                gate.verify(self.approval_row(), HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")


if __name__ == "__main__":
    unittest.main()
