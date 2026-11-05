"""Regression tests for exact-SHA, run-scoped native Paperclip release admission."""
import unittest
from paperclip_native_release_gate import Denied, verify

REPO="miloszspyrka-code/zar-i-szlif"
HEAD="a"*40
MERGE="b"*40
PR=155

def valid():
    return dict(
        external_id=f"{REPO}#{PR}",url=f"https://github.com/{REPO}/pull/{PR}",
        provider="github",work_product_type="pull_request",
        issue_id="issue-id",issue_status="done",execution_status="completed",
        last_outcome="approved",decision_outcome="approved",decision_stage_type="review",
        decision_id="native-decision",last_decision_id="native-decision",
        metadata_decision_id="native-decision",decision_stage_id="review-stage",
        reviewer_id="cto",producer_agent_id="engineer",return_assignee="engineer",
        eligible_reviewers=["cto"],completed_stage_ids=["review-stage"],
        reviewer_run_id="review-run",reviewer_run_agent_id="cto",
        reviewer_run_issue_id="issue-id",producer_run_id="source-run",
        producer_issue_id="issue-id",product_status="merged",review_state="approved",
        head_sha=HEAD,accepted_head_sha=HEAD,merge_commit_sha=MERGE)

class NativeReleaseGateTests(unittest.TestCase):
    def permit(self, row):
        return verify([row],REPO,PR,HEAD,MERGE)

    def test_exact_positive_review(self):
        x=self.permit(valid())
        self.assertTrue(x["verified"])
        self.assertEqual(x["decision_id"],"native-decision")

    def test_missing_or_duplicate_work_product_fails(self):
        for rows in ([],[valid(),valid()]):
            with self.subTest(rows=len(rows)),self.assertRaises(Denied):
                verify(rows,REPO,PR,HEAD,MERGE)

    def test_wrong_review_identity_or_run_fails(self):
        bad=[("last_outcome","changes_requested"),("decision_outcome","changes_requested"),
             ("metadata_decision_id","forged"),("decision_id","forged"),
             ("reviewer_id","engineer"),("eligible_reviewers",["engineer"]),
             ("completed_stage_ids",[]),("reviewer_run_agent_id","foreign"),
             ("reviewer_run_issue_id","foreign-issue"),
             ("producer_issue_id","foreign-issue"),("return_assignee","foreign")]
        for field,value in bad:
            with self.subTest(field=field),self.assertRaises(Denied):
                x=valid();x[field]=value;self.permit(x)

    def test_stale_sha_or_unmerged_product_fails(self):
        bad=[("head_sha","c"*40),("accepted_head_sha","c"*40),
             ("merge_commit_sha","d"*40),("product_status","ready_for_review"),
             ("review_state","needs_board_review"),("external_id",f"{REPO}#1"),
             ("url","https://example.invalid/pr/155")]
        for field,value in bad:
            with self.subTest(field=field),self.assertRaises(Denied):
                x=valid();x[field]=value;self.permit(x)

    def test_wrong_repository_and_invalid_sha_fails(self):
        for repo,head in (("attacker/repo",HEAD),(REPO,"untrusted")):
            with self.assertRaises(Denied): verify([valid()],repo,PR,head,MERGE)

if __name__ == "__main__":
    unittest.main()
