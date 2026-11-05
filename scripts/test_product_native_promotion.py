"""Fail-closed tests for native-reviewed product source -> ci-approved promotion."""
import unittest
from unittest.mock import patch
import product_native_promotion as p

OLD="a"*40
NEW="b"*40
MID="c"*40
SOURCE="d"*40

class ProductPromotionTests(unittest.TestCase):
    def test_noop_when_main_already_deployed(self):
        with patch.object(p,"ref",side_effect=[OLD,OLD]),patch.object(p,"live_release",return_value=OLD),\
             patch.object(p,"candidate_history",side_effect=AssertionError("must not probe release")):
            self.assertEqual(p.process(plan=True)["result"],"already_released")

    def test_one_reviewed_main_merge_admissible_plan_does_not_write(self):
        with patch.object(p,"ref",side_effect=[NEW,OLD,NEW,OLD]),\
             patch.object(p,"live_release",return_value=OLD),\
             patch.object(p,"candidate_history",return_value=[{"pr":12,"head":SOURCE,"merge":NEW}]),\
             patch.object(p,"github_api",side_effect=AssertionError("no GitHub write")):
            r=p.process(plan=True)
        self.assertEqual(r["result"],"admissible")
        self.assertEqual(r["reviewed_prs"],[12])

    def test_release_uses_nonforce_only_and_exact_remote_readback(self):
        observed=[]
        def api(path,method="get",body=None):
            observed.append((path,method,body))
            return {}
        with patch.object(p,"ref",side_effect=[NEW,OLD,NEW,OLD,NEW]),\
             patch.object(p,"live_release",side_effect=[OLD,NEW]),\
             patch.object(p,"candidate_history",return_value=[{"pr":12,"head":SOURCE,"merge":NEW}]),\
             patch.object(p,"github_api",side_effect=api),\
             patch.object(p,"save") as save,\
             patch.object(p.time,"sleep",side_effect=AssertionError("unexpected sleep")):
            result=p.process(plan=False)
        self.assertEqual(result["result"],"deployed")
        self.assertEqual(result["sha"],NEW)
        self.assertEqual(observed,[(f"/repos/{p.REPO}/git/refs/heads/ci-approved","patch",{"sha":NEW,"force":False})])
        self.assertEqual(save.call_args[0][0]["previous_sha"],OLD)

    def test_provenance_denies_unreviewed_main_direct_commit(self):
        with patch.object(p,"commit",return_value={"sha":NEW,"parents":[{"sha":OLD}]}):
            with self.assertRaisesRegex(p.Denied,"non_merge_commit"):
                p.candidate_history(OLD,NEW)

    def test_every_new_merge_must_be_independently_accepted(self):
        parents={
            NEW:{"sha":NEW,"parents":[{"sha":MID},{"sha":SOURCE}]},
            MID:{"sha":MID,"parents":[{"sha":OLD},{"sha":SOURCE}]},
        }
        with patch.object(p,"commit",side_effect=lambda sha:parents[sha]),\
             patch.object(p,"provenance",side_effect=lambda sha:(12,SOURCE) if sha==MID else (13,SOURCE)),\
             patch.object(p,"checks") as checks,\
             patch.object(p,"native_approval",side_effect=lambda pr,head,merge: (_ for _ in ()).throw(p.Denied("missing_review")) if pr==12 else None):
            with self.assertRaisesRegex(p.Denied,"missing_review"):
                p.candidate_history(OLD,NEW)
            self.assertEqual(checks.call_count,2)

    def test_direct_release_denied_when_production_drifted(self):
        with patch.object(p,"ref",side_effect=[NEW,OLD]),patch.object(p,"live_release",return_value=SOURCE):
            with self.assertRaisesRegex(p.Denied,"production_not_at_current_release_ref"):
                p.process(plan=True)

    def test_changed_main_during_approval_denies(self):
        with patch.object(p,"ref",side_effect=[NEW,OLD,MID,OLD]),\
             patch.object(p,"live_release",return_value=OLD),\
             patch.object(p,"candidate_history",return_value=[{"pr":12,"head":SOURCE,"merge":NEW}]),\
             patch.object(p,"github_api",side_effect=AssertionError("no write")):
            with self.assertRaisesRegex(p.Denied,"git_ref_race"):
                p.process(plan=False)

    def test_duplicate_or_wrong_pr_denied(self):
        row={"number":12,"head":{"sha":SOURCE},"base":{"ref":"main"},"merged_at":"2026-01-01T00:00:00Z","merge_commit_sha":NEW}
        for candidates in ([],[row,row],[{**row,"base":{"ref":"e2e"}}]):
            with self.subTest(candidates=candidates),patch.object(p,"github_api",return_value=candidates):
                with self.assertRaisesRegex(p.Denied,"missing_or_ambiguous_main_pr"):
                    p.provenance(NEW)

    def test_missing_ci_status_and_incomplete_pagination_denied(self):
        scenarios=[{"check_runs":[],"total_count":0},
                   {"check_runs":[{"name":"validate-product","status":"in_progress","conclusion":None}],"total_count":1},
                   {"check_runs":[{"name":"validate-product","status":"completed","conclusion":"success"}],"total_count":9}]
        for row in scenarios:
            with self.subTest(row=row),patch.object(p,"github_api",return_value=row):
                with self.assertRaises(p.Denied):
                    p.checks(SOURCE)

    def test_missing_native_gate_fails_closed(self):
        with patch.object(p,"NATIVE_GATE",p.Path("/__missing_paperclip_gate__/none.py")):
            with self.assertRaisesRegex(p.Denied,"native_gate_not_installed"):
                p.native_approval(12,SOURCE,NEW)

    def test_invalid_git_ref_update_fails_even_before_github_contact(self):
        for body in ({"sha":NEW,"force":True},{"sha":"invalid","force":False},{"sha":NEW}):
            with self.subTest(body=body), self.assertRaises(p.Denied):
                p.github_api(f"/repos/{p.REPO}/git/refs/heads/ci-approved",method="patch",body=body)

    def test_repository_allowlist_rejects_foreign(self):
        with self.assertRaisesRegex(p.Denied,"unsafe_github_resource"):
            p.github_api("/repos/foreign/repo/commits/"+SOURCE)

    def test_failed_secondary_check_denies_promotion(self):
        checks=[{"name":"validate-product","status":"completed","conclusion":"success"},
                {"name":"security-scan","status":"completed","conclusion":"failure"}]
        with patch.object(p,"github_api",return_value={"check_runs":checks,"total_count":2}):
            with self.assertRaisesRegex(p.Denied,"nonpassing_checks"):
                p.checks(SOURCE)

    def test_unsupported_github_method_denied(self):
        with self.assertRaisesRegex(p.Denied,"unsafe_github_method"):
            p.github_api("/repos/"+p.REPO+"/commits/"+SOURCE,method="delete")

    def test_invalid_database_container_denied_before_execution(self):
        gate=__import__("paperclip_native_release_gate")
        with patch.object(p,"run",side_effect=AssertionError("must not execute")):
            with self.assertRaisesRegex(gate.Denied,"invalid_database_container"):
                gate.read_rows(p.REPO,155,"bad/name")

if __name__=="__main__":
    unittest.main()
