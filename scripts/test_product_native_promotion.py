"""Fail-closed tests for native-reviewed product source -> ci-approved promotion."""
import json
import tempfile
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
             patch.object(p,"require_verified_local_image_delivery"),\
             patch.object(p,"save") as save,\
             patch.object(p.time,"sleep",side_effect=AssertionError("unexpected sleep")):
            result=p.process(plan=False)
        self.assertEqual(result["result"],"deployed")
        self.assertEqual(result["sha"],NEW)
        self.assertEqual(observed,[(f"/repos/{p.REPO}/git/refs/heads/ci-approved","patch",{"sha":NEW,"force":False})])
        self.assertEqual(save.call_args[0][0]["previous_sha"],OLD)

    def test_provenance_denies_unreviewed_main_direct_commit(self):
        with patch.object(p,"commit",return_value={"sha":NEW,"parents":[{"sha":OLD}]}),\
             patch.object(p,"provenance",side_effect=p.Denied("missing_or_ambiguous_main_pr")):
            with self.assertRaisesRegex(p.Denied,"missing_or_ambiguous_main_pr"):
                p.candidate_history(OLD,NEW)

    def test_every_new_merge_must_be_independently_accepted(self):
        parents={
            NEW:{"sha":NEW,"parents":[{"sha":MID},{"sha":SOURCE}]},
            MID:{"sha":MID,"parents":[{"sha":OLD},{"sha":SOURCE}]},
        }
        with patch.object(p,"commit",side_effect=lambda sha:parents[sha]),\
             patch.object(p,"provenance",side_effect=lambda sha:(12,SOURCE) if sha==MID else (13,SOURCE)),\
             patch.object(p,"checks",return_value={"billing_blocked":False}) as checks,\
             patch.object(p,"native_approval",side_effect=lambda pr,head,merge: (_ for _ in ()).throw(p.Denied("missing_review")) if pr==12 else None):
            with self.assertRaisesRegex(p.Denied,"missing_review"):
                p.candidate_history(OLD,NEW)
            self.assertEqual(checks.call_count,4)

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

    def test_patch_payload_is_escaped_json_decoded_as_php_associative_array(self):
        import json
        from types import SimpleNamespace
        observed=[]
        def fake_run(argv,timeout=30,allow_fail=False):
            observed.append(argv)
            return SimpleNamespace(stdout='{"http":200,"data":{}}',returncode=0)
        body={"sha":NEW,"force":False}
        with patch.object(p,"run",side_effect=fake_run):
            p.github_api(f"/repos/{p.REPO}/git/refs/heads/ci-approved",method="patch",body=body)
        self.assertEqual(len(observed),1)
        php=observed[0][-1]
        expected="json_decode(" + json.dumps(json.dumps(body)) + ", true)"
        self.assertIn(expected,php)
        self.assertNotIn("patch(" + json.dumps("/repos/"+p.REPO+"/git/refs/heads/ci-approved") + ", {",php)

    def attestation(self, **overrides):
        data = {"sha": SOURCE, "exit_code": 0, "runner": "zis-local-build",
                "source": "product_local_ci", "verified_at": "2026-11-16T15:05Z"}
        data.update(overrides)
        return data

    def write_attestation(self, directory, data):
        p.Path(directory, SOURCE + ".json").write_text(json.dumps(data), encoding="utf-8")

    def test_local_ci_attestation_accepts_exact_root_owned_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write_attestation(tmp, self.attestation())
            with patch.object(p, "LOCAL_CI_DIR", p.Path(tmp)):
                self.assertEqual(p.local_ci_attestation(SOURCE)["sha"], SOURCE)

    def test_local_ci_attestation_negative_controls(self):
        cases = {
            "local_ci_attestation_sha_mismatch": {"sha": NEW},
            "local_ci_attestation_not_green": {"exit_code": 1},
            "local_ci_attestation_runner_untrusted": {"runner": "untrusted-runner"},
            "local_ci_attestation_source_untrusted": {"source": "untrusted-source"},
            "local_ci_attestation_undated": {"verified_at": ""},
        }
        for reason, override in cases.items():
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                self.write_attestation(tmp, self.attestation(**override))
                with patch.object(p, "LOCAL_CI_DIR", p.Path(tmp)):
                    with self.assertRaisesRegex(p.Denied, reason):
                        p.local_ci_attestation(SOURCE)

    def test_local_ci_attestation_missing_and_unreadable_deny(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(p, "LOCAL_CI_DIR", p.Path(tmp)):
                with self.assertRaisesRegex(p.Denied, "local_ci_attestation_missing"):
                    p.local_ci_attestation(SOURCE)
            p.Path(tmp, SOURCE + ".json").write_text("{not json", encoding="utf-8")
            with patch.object(p, "LOCAL_CI_DIR", p.Path(tmp)):
                with self.assertRaisesRegex(p.Denied, "local_ci_attestation_unreadable"):
                    p.local_ci_attestation(SOURCE)

    def test_never_started_billing_blocked_needs_the_exact_billing_annotation(self):
        run = {"id": 7, "status": "completed", "conclusion": "failure",
               "started_at": "2026-11-16T14:55:09Z", "completed_at": "2026-11-16T14:55:11Z"}
        billing = {"annotation_level": "failure", "message": "The job was not started because recent account payments have failed or your spending limit needs to be increased."}
        notice = {"annotation_level": "notice", "message": "ubuntu-latest label migration"}
        real = {"annotation_level": "failure", "message": "Process completed with exit code 1."}
        with patch.object(p, "github_api", return_value=[billing, notice]):
            self.assertTrue(p.never_started_billing_blocked(run))
        for annotations in ([real], [billing, real], []):
            with self.subTest(annotations=annotations), patch.object(p, "github_api", return_value=annotations):
                self.assertFalse(p.never_started_billing_blocked(run))
        long_run = {**run, "completed_at": "2026-11-16T15:30:00Z"}
        with patch.object(p, "github_api", return_value=[billing]):
            self.assertFalse(p.never_started_billing_blocked(long_run))
        self.assertFalse(p.never_started_billing_blocked({**run, "conclusion": "success", "started_at": None}))

    def test_checks_reports_billing_block_never_as_pass(self):
        run = {"id": 7, "name": "validate-product", "status": "completed", "conclusion": "failure",
               "started_at": "2026-11-16T14:55:09Z", "completed_at": "2026-11-16T14:55:11Z"}
        with patch.object(p, "never_started_billing_blocked", return_value=True), \
             patch.object(p, "github_api", return_value={"check_runs": [run], "total_count": 1}):
            self.assertEqual(p.checks(SOURCE), {"billing_blocked": True})
        with patch.object(p, "never_started_billing_blocked", return_value=False), \
             patch.object(p, "github_api", return_value={"check_runs": [run], "total_count": 1}):
            with self.assertRaisesRegex(p.Denied, "product_ci_not_green"):
                p.checks(SOURCE)
        green = {"id": 8, "name": "validate-product", "status": "completed", "conclusion": "success"}
        with patch.object(p, "github_api", return_value={"check_runs": [green], "total_count": 1}):
            self.assertEqual(p.checks(SOURCE), {"billing_blocked": False})

    def history_nodes(self, head_tree, merge_tree):
        node = {"sha": NEW, "parents": [{"sha": OLD}], "files": [{"filename": "app/web/index.html", "status": "modified"}],
                "commit": {"tree": {"sha": merge_tree}}}
        head = {"sha": SOURCE, "commit": {"tree": {"sha": head_tree}}}
        return lambda sha: {NEW: node, SOURCE: head}.get(sha, {"sha": sha})

    def test_billing_blocked_runtime_merge_uses_exact_sha_attestation(self):
        with patch.object(p, "commit", side_effect=self.history_nodes("t" * 40, "t" * 40)), \
             patch.object(p, "provenance", return_value=(178, SOURCE)), \
             patch.object(p, "checks", return_value={"billing_blocked": True}), \
             patch.object(p, "local_ci_attestation", return_value={"sha": SOURCE}) as attestation, \
             patch.object(p, "native_approval"):
            self.assertEqual(p.candidate_history(OLD, NEW), [
                {"pr": 178, "head": SOURCE, "merge": NEW, "ci_evidence": "local_ci_attestation"}])
        attestation.assert_called_once_with(SOURCE)

    def test_attestation_never_replaces_native_approval(self):
        with patch.object(p, "commit", side_effect=self.history_nodes("t" * 40, "t" * 40)), \
             patch.object(p, "provenance", return_value=(178, SOURCE)), \
             patch.object(p, "checks", return_value={"billing_blocked": True}), \
             patch.object(p, "local_ci_attestation", return_value={"sha": SOURCE}), \
             patch.object(p, "native_approval", side_effect=p.Denied("native_approval_unverified")):
            with self.assertRaisesRegex(p.Denied, "native_approval_unverified"):
                p.candidate_history(OLD, NEW)

    def test_billing_blocked_without_attestation_denies(self):
        with patch.object(p, "commit", side_effect=self.history_nodes("t" * 40, "t" * 40)), \
             patch.object(p, "provenance", return_value=(178, SOURCE)), \
             patch.object(p, "checks", return_value={"billing_blocked": True}), \
             patch.object(p, "local_ci_attestation", side_effect=p.Denied("local_ci_attestation_missing")), \
             patch.object(p, "native_approval", side_effect=AssertionError("must not be reached")):
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_missing"):
                p.candidate_history(OLD, NEW)

    def test_billing_blocked_with_tree_drift_denies(self):
        with patch.object(p, "commit", side_effect=self.history_nodes("t" * 40, "u" * 40)), \
             patch.object(p, "provenance", return_value=(178, SOURCE)), \
             patch.object(p, "checks", return_value={"billing_blocked": True}), \
             patch.object(p, "local_ci_attestation", return_value={"sha": SOURCE}), \
             patch.object(p, "native_approval", side_effect=AssertionError("must not be reached")):
            with self.assertRaisesRegex(p.Denied, "head_merge_tree_mismatch"):
                p.candidate_history(OLD, NEW)

    def test_docs_only_merge_stays_strict_under_billing_block(self):
        node = {"sha": NEW, "parents": [{"sha": OLD}], "files": [{"filename": "docs/RELEASE-POLICY.md", "status": "modified"}],
                "commit": {"tree": {"sha": "t" * 40}}}
        with patch.object(p, "commit", side_effect=lambda sha: node if sha == NEW else {"sha": sha}), \
             patch.object(p, "provenance", return_value=(178, SOURCE)), \
             patch.object(p, "checks", return_value={"billing_blocked": True}), \
             patch.object(p, "local_ci_attestation", side_effect=AssertionError("must not be reached")):
            with self.assertRaisesRegex(p.Denied, "product_ci_not_green"):
                p.candidate_history(OLD, NEW)

if __name__=="__main__":
    unittest.main()
