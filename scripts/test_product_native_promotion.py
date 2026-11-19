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
             patch.object(p,"provenance",side_effect=lambda sha:(12,SOURCE,"ZARI-240") if sha==MID else (13,SOURCE,"ZARI-240")),\
             patch.object(p,"checks") as checks,\
             patch.object(p,"native_approval",side_effect=lambda pr,head,merge,issue: (_ for _ in ()).throw(p.Denied("missing_review")) if pr==12 else None):
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

    def test_missing_trusted_ci_receipt_never_executes_source_as_root(self):
        with patch.object(p,"local_ci_attestation",return_value=None),\
             patch.object(p,"run",side_effect=AssertionError("ROOT CODE EXECUTION")),\
             patch.object(p,"github_api",side_effect=AssertionError("provider call")):
            with self.assertRaisesRegex(p.Denied,"trusted_rootless_ci_attestation_missing"):
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

    def test_root_owned_sha_bound_attestation_is_read_only(self):
        with patch.object(p,"local_ci_attestation",return_value={"sha":SOURCE,"tree":NEW}),\
             patch.object(p,"commit",return_value={"commit":{"tree":{"sha":NEW}}}),\
             patch.object(p,"run",side_effect=AssertionError("source must not run")):
            self.assertIsNone(p.checks(SOURCE))

    def test_github_tree_mismatch_denies_even_signed_receipt(self):
        with patch.object(p,"local_ci_attestation",return_value={"sha":SOURCE,"tree":NEW}),\
             patch.object(p,"commit",return_value={"commit":{"tree":{"sha":MID}}}):
            with self.assertRaisesRegex(p.Denied,"trusted_rootless_ci_tree_mismatch"):
                p.checks(SOURCE)

    def test_signed_rootless_receipt_rejects_tamper_legacy_and_stale(self):
        import hashlib, hmac, json
        from datetime import datetime, timezone
        key=bytes(range(32))
        now=1760000000.0
        timestamp=datetime.fromtimestamp(now,timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        evidence={"schema_version":2,"sha":SOURCE,"tree":NEW,
                  "runner":"zis-ci-guest-rootless","runner_uid":991,
                  "command":p.ROOTLESS_CI_COMMAND,"exit_code":0,
                  "log_sha256":"e"*64,"verified_at":timestamp}
        signature=hmac.new(key,json.dumps(evidence,sort_keys=True,separators=(",",":"),
                     ensure_ascii=True).encode(),hashlib.sha256).hexdigest()
        receipt=dict(evidence,signature=signature)
        self.assertTrue(p.verify_rootless_receipt(SOURCE,receipt,key,now=now))
        for field,value in (("sha",MID),("tree",MID),("runner_uid",0),
                            ("exit_code",1),("schema_version",1),
                            ("command","npm run validate:code")):
            with self.subTest(field=field):
                self.assertFalse(p.verify_rootless_receipt(SOURCE,dict(receipt,**{field:value}),key,now=now))
        self.assertFalse(p.verify_rootless_receipt(SOURCE,receipt,key,now=now+8*86400))
        self.assertFalse(p.verify_rootless_receipt(SOURCE,receipt,key,now=now-600))
        self.assertFalse(p.verify_rootless_receipt(SOURCE,receipt,b"bad",now=now))
        self.assertFalse(p.verify_rootless_receipt(SOURCE,evidence,key,now=now))

    def test_runtime_review_rejection_precedes_any_ci_check(self):
        with patch.object(p,"commit",return_value={"sha":NEW,"parents":[{"sha":OLD}]}),\
             patch.object(p,"provenance",return_value=(13,SOURCE,"ZARI-240")),\
             patch.object(p,"non_runtime_files_only",return_value=False),\
             patch.object(p,"native_approval",side_effect=p.Denied("review_missing")),\
             patch.object(p,"checks",side_effect=AssertionError("CI before review")):
            with self.assertRaisesRegex(p.Denied,"review_missing"):
                p.candidate_history(OLD,NEW)


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

if __name__=="__main__":
    unittest.main()
