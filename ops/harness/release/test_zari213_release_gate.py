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

    def test_harness_query_has_workspace_anchored_read_only_security_gate(self):
        sql = gate.query(HARNESS, 215, "ZARI-213")
        self.assertIn("'issue_count', COUNT(*)", sql)
        self.assertIn("workspace_id='" + gate.WORKSPACE + "'", sql)
        self.assertIn("number=213", sql)
        self.assertIn("z.status = 'done'", sql)
        self.assertIn("jsonb_typeof(z.metadata->'security_hold') = 'boolean'", sql)
        self.assertIn("z.metadata->'security_hold' = 'false'::jsonb", sql)
        self.assertIn("AS zari213_release_state", sql)
        self.assertFalse(any(
            word in sql.upper()
            for word in ("INSERT INTO", "UPDATE ", "DELETE FROM", "ALTER TABLE", "DROP TABLE")
        ))

    def test_product_query_does_not_apply_harness_security_hold(self):
        sql = gate.query(PRODUCT, 215, "ZARI-190")
        self.assertIn("NULL::json AS zari213_release_state", sql)
        self.assertNotIn("z.workspace_id='" + gate.WORKSPACE + "'", sql)
        self.assertNotIn("'issue_count', COUNT(*)", sql)

    def test_stale_or_malformed_sha_denied(self):
        with self.assertRaisesRegex(gate.Denied, "invalid_sha"):
            gate.validate_input(HARNESS, 215, "abc", MERGE, "ZARI-213")

    def test_wrong_issue_ref_denied(self):
        with self.assertRaisesRegex(gate.Denied, "invalid_issue_ref"):
            gate.validate_input(HARNESS, 215, HEAD, MERGE, "213")

    def released_security_state(self):
        return {
            "issue_count": 1,
            "status_done": True,
            "security_hold_is_boolean": True,
            "security_hold_is_false": True,
        }

    def approval_row(self, *, status="in_review", reviewer=CTO, producer=HE,
                     repo=HARNESS, issue_number=213, security_state="released",
                     include_security_state=True):
        row = {
            "issue_id": "01a1e0ac-5d9e-7c46-8add-67be5ff69dcc",
            "issue_number": issue_number,
            "issue_description": "Canonical https://github.com/" + repo + "/pull/215",
            "issue_status": status,
            "producer_id": producer,
            "producer_runs": 1,
            "comments": [{
                "author_type": "agent",
                "author_id": reviewer,
                "content": "RELEASE_APPROVED " + HEAD + "\nREPOSITORY " + repo + "\nPR 215\nPRODUCER " + producer,
                "source_task_id": TASK,
                "created_at": "2026-11-22T15:00:00Z",
            }],
        }
        if include_security_state:
            row["zari213_release_state"] = (
                self.released_security_state() if security_state == "released" else security_state
            )
        return row

    def test_security_hold_fails_before_approval(self):
        with self.assertRaisesRegex(gate.Denied, "issue_not_reviewable"):
            gate.verify(self.approval_row(status="blocked"), HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_explicit_done_and_false_hold_is_admitted(self):
        with patch.object(gate, "task_record", return_value={
            "agent_id": CTO, "issue_id": "01a1e0ac-5d9e-7c46-8add-67be5ff69dcc", "status": "completed"
        }):
            outcome = gate.verify(self.approval_row(status="done"), HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")
        self.assertTrue(outcome["verified"])

    def test_true_hold_blocks_even_when_zari213_is_done(self):
        state = {
            "issue_count": 1, "status_done": True,
            "security_hold_is_boolean": True, "security_hold_is_false": False,
        }
        row = self.approval_row(status="done", security_state=state)
        with self.assertRaisesRegex(gate.Denied, "zari213_security_hold_active"):
            gate.verify(row, HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_missing_security_gate_result_fails_closed(self):
        row = self.approval_row(status="done", include_security_state=False)
        with self.assertRaisesRegex(gate.Denied, "zari213_security_hold_active"):
            gate.verify(row, HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_missing_security_hold_field_fails_closed(self):
        state = {
            "issue_count": 1, "status_done": True,
            "security_hold_is_boolean": False, "security_hold_is_false": False,
        }
        with self.assertRaisesRegex(gate.Denied, "zari213_security_hold_active"):
            gate.verify(self.approval_row(status="done", security_state=state),
                        HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_wrong_security_hold_type_fails_closed(self):
        state = {
            "issue_count": 1, "status_done": True,
            "security_hold_is_boolean": 1, "security_hold_is_false": True,
        }
        with self.assertRaisesRegex(gate.Denied, "zari213_security_hold_active"):
            gate.verify(self.approval_row(status="done", security_state=state),
                        HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_absent_canonical_issue_fails_closed(self):
        state = {
            "issue_count": 0, "status_done": False,
            "security_hold_is_boolean": False, "security_hold_is_false": False,
        }
        with self.assertRaisesRegex(gate.Denied, "zari213_security_hold_active"):
            gate.verify(self.approval_row(status="done", security_state=state),
                        HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_duplicate_canonical_issues_fail_closed(self):
        state = {
            "issue_count": 2, "status_done": True,
            "security_hold_is_boolean": True, "security_hold_is_false": True,
        }
        with self.assertRaisesRegex(gate.Denied, "zari213_security_hold_active"):
            gate.verify(self.approval_row(status="done", security_state=state),
                        HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_hold_denial_precedes_target_issue_status(self):
        state = {
            "issue_count": 1, "status_done": True,
            "security_hold_is_boolean": True, "security_hold_is_false": False,
        }
        with self.assertRaisesRegex(gate.Denied, "zari213_security_hold_active"):
            gate.verify(self.approval_row(status="blocked", security_state=state),
                        HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_product_release_is_not_blocked_by_harness_security_hold(self):
        row = self.approval_row(
            status="done", repo=PRODUCT, issue_number=190, include_security_state=False
        )
        with patch.object(gate, "task_record", return_value={
            "agent_id": CTO, "issue_id": row["issue_id"], "status": "completed"
        }):
            outcome = gate.verify(row, PRODUCT, 215, HEAD, MERGE, "ZARI-190", "fake")
        self.assertTrue(outcome["verified"])

    def test_independent_exact_sha_review_can_pass(self):
        with patch.object(gate, "task_record", return_value={"agent_id": CTO, "issue_id": "01a1e0ac-5d9e-7c46-8add-67be5ff69dcc", "status": "completed"}):
            outcome = gate.verify(self.approval_row(), HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")
        self.assertTrue(outcome["verified"])
        self.assertEqual(outcome["head_sha"], HEAD)

    def test_self_review_rejected(self):
        with self.assertRaisesRegex(gate.Denied, "not_independent"):
            gate.verify(self.approval_row(producer=CTO), HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_cho_and_ceo_cannot_replace_cto(self):
        for agent in ("19eb944f-ff52-4fbd-ba67-56924764591b",
                      "b7948572-3cee-4ca5-84b9-8352f9375c4f"):
            with self.subTest(agent=agent), self.assertRaisesRegex(gate.Denied, "reviewer_not_authorized"):
                gate.verify(self.approval_row(reviewer=agent), HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_foreign_reviewer_task_issue_denied(self):
        with patch.object(gate, "task_record", return_value={
            "agent_id": CTO, "issue_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "status": "completed"
        }):
            with self.assertRaisesRegex(gate.Denied, "reviewer_task_issue_mismatch"):
                gate.verify(self.approval_row(), HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_wrong_pr_in_issue_denied(self):
        row = self.approval_row()
        row["issue_description"] = "https://github.com/" + HARNESS + "/pull/2150"
        with self.assertRaisesRegex(gate.Denied, "issue_pr_link_missing"):
            gate.verify(row, HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_wrong_pr_in_approval_denied(self):
        row = self.approval_row()
        row["comments"][0]["content"] = row["comments"][0]["content"].replace("PR 215", "PR 216")
        with self.assertRaisesRegex(gate.Denied, "missing_release_approval"):
            gate.verify(row, HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_wrong_repo_in_approval_denied(self):
        row = self.approval_row()
        row["comments"][0]["content"] = row["comments"][0]["content"].replace("REPOSITORY " + HARNESS, "REPOSITORY " + PRODUCT)
        with self.assertRaisesRegex(gate.Denied, "missing_release_approval"):
            gate.verify(row, HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_wrong_issue_number_denied(self):
        row = self.approval_row()
        row["issue_number"] = 999
        with self.assertRaisesRegex(gate.Denied, "issue_reference_mismatch"):
            gate.verify(row, HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")

    def test_uncompleted_reviewer_task_rejected(self):
        with patch.object(gate, "task_record", return_value={"agent_id": CTO, "issue_id": "01a1e0ac-5d9e-7c46-8add-67be5ff69dcc", "status": "running"}):
            with self.assertRaisesRegex(gate.Denied, "reviewer_task_not_completed"):
                gate.verify(self.approval_row(), HARNESS, 215, HEAD, MERGE, "ZARI-213", "fake")


if __name__ == "__main__":
    unittest.main()
