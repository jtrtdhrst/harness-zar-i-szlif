"""Fail-closed tests for native-reviewed product source -> ci-approved promotion."""
import contextlib
import itertools
import json
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import product_native_promotion as p

OLD="a"*40
NEW="b"*40
MID="c"*40
SOURCE="d"*40

class ProductPromotionTests(unittest.TestCase):
    def test_noop_when_main_already_deployed(self):
        with patch.object(p,"ref",side_effect=[OLD,OLD,OLD,OLD]),patch.object(p,"live_release",return_value=OLD),\
             patch.object(p,"candidate_history",side_effect=AssertionError("must not probe release")):
            self.assertEqual(p.process(plan=True)["result"],"already_released")

    def test_already_released_denies_stale_live_read_ref_race(self):
        # The live HTTP read may outlast a main/release branch move.
        for after_live in ((NEW, OLD), (OLD, NEW)):
            with self.subTest(after_live=after_live):
                with patch.object(p, "ref", side_effect=[OLD, OLD, *after_live]), \
                     patch.object(p, "live_release", return_value=OLD), \
                     patch.object(p, "candidate_history", side_effect=AssertionError("no scan")), \
                     patch.object(p, "github_api", side_effect=AssertionError("no write")):
                    with self.assertRaisesRegex(p.Denied, "git_ref_race"):
                        p.process(plan=False)

    def test_non_runtime_noop_denies_main_or_release_ref_race(self):
        # A direct metadata-only commit may be followed by a runtime commit
        # before the history walk ends. Never report stale no_runtime_release_required.
        for after_scan in ((MID, OLD), (NEW, MID)):
            with self.subTest(after_scan=after_scan):
                with patch.object(p, "ref", side_effect=[NEW, OLD, *after_scan]), \
                     patch.object(p, "live_release", return_value=OLD), \
                     patch.object(p, "candidate_history", return_value=[]), \
                     patch.object(p, "github_api", side_effect=AssertionError("no provider writes")):
                    with self.assertRaisesRegex(p.Denied, "git_ref_race"):
                        p.process(plan=False)

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


    def test_three_exact_historic_metadata_direct_commits_are_noop(self):
        rows = p.HISTORIC_METADATA_ONLY
        nodes = {
            sha: {"sha": sha, "parents": [{"sha": spec["parent"]}],
                  "files": [{"status": status, "filename": path}
                            for status, path in spec["files"]]}
            for sha, spec in rows.items()
        }
        start = "63441d5d3056f4845d4bfcaf908429f8f09d620f"
        prior = "4feef6903dc21be5da0433a77b10549bf0009661"
        with patch.object(p, "commit", side_effect=lambda sha: nodes[sha]), \
             patch.object(p, "provenance", side_effect=AssertionError("no PR lookup for known harmless metadata")), \
             patch.object(p, "checks", side_effect=AssertionError("no CI for harmless metadata")), \
             patch.object(p, "native_approval", side_effect=AssertionError("no runtime review needed")):
            self.assertEqual(p.candidate_history(prior, start), [])
            with patch.object(p, "ref", side_effect=[start, prior, start, prior]), \
                 patch.object(p, "live_release", return_value=prior), \
                 patch.object(p, "github_api", side_effect=AssertionError("must not update release branch")):
                result = p.process(plan=False)
                self.assertEqual(result["result"], "no_runtime_release_required")
                self.assertEqual(result["release_ref"], prior)

    def test_historic_metadata_identity_and_file_list_fail_closed(self):
        for sha, spec in p.HISTORIC_METADATA_ONLY.items():
            good = {"sha": sha, "files": [{"status": status, "filename": path}
                                            for status, path in spec["files"]]}
            self.assertTrue(p.known_metadata_only_direct_commit(sha, good, spec["parent"]))
            corrupt = [
                ({**good, "sha": "f"*40}, spec["parent"]),
                (good, "a"*40),
                ({**good, "files": []}, spec["parent"]),
                ({**good, "files": good["files"]+[{"status":"modified","filename":"src/index.ts"}]}, spec["parent"]),
                ({**good, "files": [{**good["files"][0],"status":"added"}]+good["files"][1:]}, spec["parent"]),
            ]
            for node, parent in corrupt:
                with self.subTest(sha=sha, node=node, parent=parent):
                    with self.assertRaisesRegex(p.Denied,"historic_metadata"):
                        p.known_metadata_only_direct_commit(sha,node,parent)

    def test_future_direct_commit_with_same_paths_still_denied(self):
        self.assertFalse(p.known_metadata_only_direct_commit(
            "f"*40, {"sha":"f"*40,"files":[{"status":"removed","filename":"mcp/.gitkeep"}]},
            "63441d5d3056f4845d4bfcaf908429f8f09d620f"))
        with patch.object(p,"commit",return_value={"sha":"f"*40,"parents":[{"sha":"63441d5d3056f4845d4bfcaf908429f8f09d620f"}]}), \
             patch.object(p,"provenance",side_effect=p.Denied("missing_or_ambiguous_main_pr")):
            with self.assertRaisesRegex(p.Denied,"missing_or_ambiguous_main_pr"):
                p.candidate_history("63441d5d3056f4845d4bfcaf908429f8f09d620f","f"*40)

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

    def test_premerge_zero_checkruns_requires_rootless_receipt(self):
        empty = {"check_runs": [], "total_count": 0}
        node = {"commit": {"tree": {"sha": "e"*40}}}
        with patch.object(p, "github_api", return_value=empty), \
             patch.object(p, "commit", return_value=node), \
             patch.object(p, "premerge_rootless_attestation", return_value={}) as receipt:
            result = p.premerge_head_checks(SOURCE, node)
        self.assertTrue(result["rootless_premerge"])
        receipt.assert_called_once_with(SOURCE, "e"*40)

    def test_premerge_missing_or_failing_evidence_denies(self):
        empty = {"check_runs": [], "total_count": 0}
        node = {"commit": {"tree": {"sha": "e"*40}}}
        with patch.object(p, "github_api", return_value=empty), \
             patch.object(p, "commit", return_value=node), \
             patch.object(p, "premerge_rootless_attestation", side_effect=p.Denied("local_ci_attestation_missing")):
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_missing"):
                p.premerge_head_checks(SOURCE, node)
        broken = {"check_runs": [{"name":"validate-product","status":"completed","conclusion":"failure"}],
                  "total_count":1}
        with patch.object(p, "github_api", return_value=broken), \
             patch.object(p, "premerge_rootless_attestation") as receipt:
            with self.assertRaises(p.Denied):
                p.premerge_head_checks(SOURCE, node)
            receipt.assert_not_called()
        with patch.object(p,"checks",side_effect=p.Denied("product_ci_not_green")), \
             patch.object(p,"github_api",side_effect=p.Denied("controlled_command_failed")):
            with self.assertRaisesRegex(p.Denied, "product_ci_not_green"):
                p.premerge_head_checks(SOURCE, node)

    def test_premerge_tree_mismatch_denied(self):
        empty = {"check_runs": [], "total_count": 0}
        with patch.object(p, "github_api", return_value=empty), \
             patch.object(p, "commit",return_value={"commit":{"tree":{"sha":"a"*40}}}), \
             patch.object(p,"premerge_rootless_attestation") as receipt:
            with self.assertRaisesRegex(p.Denied, "head_merge_tree_mismatch"):
                p.premerge_head_checks(SOURCE, {"commit":{"tree":{"sha":"b"*40}}})
            receipt.assert_not_called()

    def test_premerge_receipt_requires_strict_contract_and_secure_file(self):
        tree="e"*40
        data={"schema_version":2,"sha":SOURCE,"tree":tree,
              "runner":"zis-rootless-exact-tree","source":"root-verified-systemd-e2e",
              "exit_code":0,"verified_at":"2026-11-18T13:41Z",
              "stages":{"exact_tree":True,"rootless_isolation":True,"full_product_build":True,
                        "network_none_validation":True,"final_image":True,
                        "positive_provenance":True,"negative_versionless":True}}
        with self.trusted_tree() as directory:
            path=directory/("premerge-"+SOURCE+".json")
            path.write_text(json.dumps(data));os.chmod(path,0o600)
            self.assertEqual(p.premerge_rootless_attestation(SOURCE,tree),data)
            for key,value in [("sha",NEW),("tree",NEW),
                              ("exit_code",1),("exit_code",False),
                              ("exit_code",0.0),("source","agent-reported"),
                              ("schema_version",1),("schema_version",2.0),
                              ("schema_version",True),
                              ("stages",{"exact_tree":True}),
                              ("stages",{**data["stages"],"exact_tree":1}),
                              ("stages",{**data["stages"],"exact_tree":1.0}),
                              ("stages",{**data["stages"],"network_none_validation":False}),
                              ("stages",{**data["stages"],"final_image":"true"})]:
                with self.subTest(key=key):
                    path.write_text(json.dumps({**data,key:value}))
                    with self.assertRaisesRegex(p.Denied,"premerge_attestation_invalid"):
                        p.premerge_rootless_attestation(SOURCE,tree)

    def test_missing_ci_status_and_incomplete_pagination_denied(self):
        scenarios=[{"check_runs":[],"total_count":0},
                   {"check_runs":[{"name":"validate-product","status":"in_progress","conclusion":None}],"total_count":1},
                   {"check_runs":[{"name":"validate-product","status":"completed","conclusion":"success"}],"total_count":9}]
        for row in scenarios:
            with self.subTest(row=row),patch.object(p,"github_api",return_value=row):
                with self.assertRaises(p.Denied):
                    p.checks(SOURCE)

    def test_tracked_systemd_unit_is_multica_scoped(self):
        """A future systemd reinstall must not resurrect legacy Paperclip approval."""
        unit = p.Path(__file__).resolve().parents[1] / "ops/systemd/product-native-promotion.service"
        text = unit.read_text(encoding="utf-8")
        self.assertIn("ConditionPathExists=/usr/local/libexec/multica_native_release_gate.py", text)
        self.assertIn("Environment=PRODUCT_NATIVE_GATE=/usr/local/libexec/multica_native_release_gate.py", text)
        self.assertNotIn("paperclip_native_release_gate.py", text)

    def test_native_gate_is_multica_and_sha_bound(self):
        """Never regress release authority to legacy Paperclip during controller updates."""
        from types import SimpleNamespace
        self.assertEqual(str(p.NATIVE_GATE), "/usr/local/libexec/multica_native_release_gate.py")
        with patch.object(p.Path, "is_file", return_value=True), \
             patch.object(p, "github_api", return_value={"number":12,"title":"ZARI-228: reviewed source"}), \
             patch.object(p, "run", return_value=SimpleNamespace(returncode=0)) as execute:
            p.native_approval(12, SOURCE, NEW)
        argv = execute.call_args.args[0]
        self.assertEqual(argv, [p.sys.executable,
                               "/usr/local/libexec/multica_native_release_gate.py",
                               "--repo", p.REPO, "--pr", "12",
                               "--head-sha", SOURCE, "--merge-sha", NEW,
                               "--issue-ref", "ZARI-228"])

    def test_issue_ref_is_exact_and_ambiguous_title_fails_closed(self):
        for doc in ({"number":12, "title":"runtime fix"},
                    {"number":12, "title":"ZARI-228 & ZARI-241"},
                    {"number":13, "title":"ZARI-228"},
                    {"number":True,"title":"ZARI-228"},
                    {"number":12,"title":None}):
            with self.subTest(doc=doc), \
                 patch.object(p.Path, "is_file", return_value=True), \
                 patch.object(p, "github_api", return_value=doc), \
                 patch.object(p, "run", side_effect=AssertionError("must not execute")):
                with self.assertRaises(p.Denied):
                    p.native_approval(12, SOURCE, NEW)

    def test_missing_native_gate_fails_closed(self):
        with patch.object(p,"NATIVE_GATE",p.Path("/__missing_multica_gate__/none.py")):
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

    @contextlib.contextmanager
    def trusted_tree(self, mode=0o700):
        """Temp attestation directory owned by the test process (root in prod)."""
        directory = p.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(directory), True)
        os.chmod(directory, mode)
        with patch.object(p, "ATTESTATION_UID", os.getuid()), \
             patch.object(p, "ATTESTATION_GID", os.getgid()), \
             patch.object(p, "LOCAL_CI_DIR", directory):
            yield directory

    def write_attestation(self, directory, data, mode=0o600):
        path = p.Path(directory, SOURCE + ".json")
        path.write_text(json.dumps(data), encoding="utf-8")
        os.chmod(path, mode)
        return path

    def test_local_ci_attestation_accepts_exact_root_owned_shape(self):
        with self.trusted_tree() as directory:
            self.write_attestation(directory, self.attestation())
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
            with self.subTest(reason=reason), self.trusted_tree() as directory:
                self.write_attestation(directory, self.attestation(**override))
                with self.assertRaisesRegex(p.Denied, reason):
                    p.local_ci_attestation(SOURCE)

    def test_local_ci_attestation_rejects_boolean_or_float_zero(self):
        for invalid in (False, 0.0, "0", None):
            with self.subTest(value=repr(invalid)), self.trusted_tree() as directory:
                self.write_attestation(directory, self.attestation(exit_code=invalid))
                with self.assertRaisesRegex(p.Denied, "local_ci_attestation_not_green"):
                    p.local_ci_attestation(SOURCE)

    def test_local_image_receipt_rejects_json_bool_numeric_coercion(self):
        valid = {"schema_version": 1, "verified": True,
                 "registry": "127.0.0.1:5000",
                 "coolify_image_app_uuid": "cs847jiwtuq5rlm8ntjeohgf",
                 "runner": "zis-local-build"}
        with patch.object(p, "Path") as mock_path:
            mock_path.return_value.is_file.return_value = True
            mock_path.return_value.read_text.return_value = json.dumps(valid)
            self.assertIsNone(p.require_verified_local_image_delivery())
            for key, value in (("schema_version", True),
                               ("schema_version", 1.0),
                               ("verified", 1),
                               ("verified", "true")):
                with self.subTest(key=key, value=value):
                    mock_path.return_value.read_text.return_value = json.dumps({**valid, key: value})
                    with self.assertRaisesRegex(p.Denied, "local_image_delivery_unverified"):
                        p.require_verified_local_image_delivery()

    def test_local_ci_attestation_missing_and_unreadable_deny(self):
        with self.trusted_tree() as directory:
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_missing"):
                p.local_ci_attestation(SOURCE)
            p.Path(directory, SOURCE + ".json").write_text("{not json", encoding="utf-8")
            os.chmod(p.Path(directory, SOURCE + ".json"), 0o600)
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_unreadable"):
                p.local_ci_attestation(SOURCE)

    def test_attestation_symlink_is_never_followed(self):
        with self.trusted_tree() as directory:
            target = self.write_attestation(directory, self.attestation())
            os.rename(target, p.Path(directory, "real.json"))
            os.symlink("real.json", p.Path(directory, SOURCE + ".json"))
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_symlink_denied"):
                p.local_ci_attestation(SOURCE)

    def test_attestation_symlink_to_absolute_target_is_denied(self):
        with self.trusted_tree() as directory, tempfile.TemporaryDirectory() as outside:
            target = p.Path(outside, SOURCE + ".json")
            target.write_text(json.dumps(self.attestation()), encoding="utf-8")
            os.chmod(target, 0o600)
            os.symlink(str(target), p.Path(directory, SOURCE + ".json"))
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_symlink_denied"):
                p.local_ci_attestation(SOURCE)

    def test_attestation_must_be_a_regular_file(self):
        with self.trusted_tree() as directory:
            os.mkdir(p.Path(directory, SOURCE + ".json"))
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_not_regular"):
                p.local_ci_attestation(SOURCE)
            os.rmdir(p.Path(directory, SOURCE + ".json"))
            os.mkfifo(p.Path(directory, SOURCE + ".json"))
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_not_regular"):
                p.local_ci_attestation(SOURCE)

    def test_attestation_group_or_world_writable_denied(self):
        for mode in (0o660, 0o602, 0o622, 0o777):
            with self.subTest(mode=oct(mode)), self.trusted_tree() as directory:
                self.write_attestation(directory, self.attestation(), mode=mode)
                with self.assertRaisesRegex(p.Denied, "local_ci_attestation_mode_untrusted"):
                    p.local_ci_attestation(SOURCE)

    def inode(self, **overrides):
        info = {"st_mode": p.stat.S_IFREG | 0o600, "st_uid": 0, "st_gid": 0,
                "st_nlink": 1, "st_size": 256}
        info.update(overrides)
        return SimpleNamespace(**info)

    def test_attestation_inode_policy_is_explicit(self):
        cases = {
            "symlink inode": ({"st_mode": p.stat.S_IFLNK | 0o777}, "local_ci_attestation_not_regular"),
            "directory inode": ({"st_mode": p.stat.S_IFDIR | 0o700}, "local_ci_attestation_not_regular"),
            "foreign owner": ({"st_uid": 1000}, "local_ci_attestation_owner_untrusted"),
            "foreign group": ({"st_gid": 1000}, "local_ci_attestation_owner_untrusted"),
            "group writable": ({"st_mode": p.stat.S_IFREG | 0o660}, "local_ci_attestation_mode_untrusted"),
            "other writable": ({"st_mode": p.stat.S_IFREG | 0o602}, "local_ci_attestation_mode_untrusted"),
            "hard linked": ({"st_nlink": 2}, "local_ci_attestation_link_untrusted"),
            "oversized": ({"st_size": p.ATTESTATION_MAX_BYTES + 1}, "local_ci_attestation_too_large"),
        }
        for label, (override, reason) in cases.items():
            with self.subTest(case=label):
                with self.assertRaisesRegex(p.Denied, reason):
                    p._require_trusted_attestation_file(self.inode(**override))

    def test_attestation_inode_policy_accepts_root_only_files(self):
        for mode in (0o600, 0o400, 0o644):
            with self.subTest(mode=oct(mode)):
                p._require_trusted_attestation_file(self.inode(st_mode=p.stat.S_IFREG | mode))

    def test_attestation_dir_policy_is_explicit(self):
        for override in ({"st_mode": p.stat.S_IFDIR | 0o777},
                         {"st_mode": p.stat.S_IFDIR | 0o770},
                         {"st_uid": 1000},
                         {"st_mode": p.stat.S_IFREG | 0o700}):
            with self.subTest(override=override):
                with self.assertRaisesRegex(p.Denied, "local_ci_attestation_dir_untrusted"):
                    p._require_trusted_attestation_dir(self.inode(**override))
        p._require_trusted_attestation_dir(self.inode(st_mode=p.stat.S_IFDIR | 0o700))

    def test_attestation_hardlink_denied(self):
        with self.trusted_tree() as directory:
            path = self.write_attestation(directory, self.attestation())
            os.link(path, p.Path(directory, "second-link.json"))
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_link_untrusted"):
                p.local_ci_attestation(SOURCE)

    def test_attestation_too_large_denied(self):
        with self.trusted_tree() as directory:
            path = p.Path(directory, SOURCE + ".json")
            path.write_text(json.dumps(self.attestation()) + " " * p.ATTESTATION_MAX_BYTES, encoding="utf-8")
            os.chmod(path, 0o600)
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_too_large"):
                p.local_ci_attestation(SOURCE)

    def test_attestation_directory_must_be_trusted(self):
        with self.trusted_tree(mode=0o777) as directory:
            self.write_attestation(directory, self.attestation())
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_dir_untrusted"):
                p.local_ci_attestation(SOURCE)

    def test_attestation_unavailable_directory_denies(self):
        with patch.object(p, "LOCAL_CI_DIR", p.Path("/__no_such_attestation_dir__")):
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_dir_unavailable"):
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

    def annotation(self, level="failure", message="m", path=".github", line=1):
        return {"annotation_level": level, "message": message, "path": path, "start_line": line}

    def failing_run(self):
        return {"id": 7, "status": "completed", "conclusion": "failure",
                "started_at": "2026-11-16T14:55:09Z", "completed_at": "2026-11-16T14:55:11Z"}

    BILLING = ("The job was not started because recent account payments have failed "
               "or your spending limit needs to be increased.")

    def test_later_page_non_billing_failure_cancels_never_started(self):
        page1 = [self.annotation(message=self.BILLING, line=i) for i in range(p.ANNOTATIONS_PAGE_SIZE)]
        page2 = [self.annotation(message="Process completed with exit code 1.", line=9001)]
        requested = []

        def fake(path):
            requested.append(path)
            return page2 if "page=2" in path else page1

        with patch.object(p, "github_api", side_effect=fake):
            self.assertFalse(p.never_started_billing_blocked(self.failing_run()))
        self.assertEqual(len(requested), 2)
        self.assertIn("page=1", requested[0])
        self.assertIn("page=2", requested[1])
        self.assertTrue(all("per_page=" + str(p.ANNOTATIONS_PAGE_SIZE) in path for path in requested))

    def test_billing_only_across_pages_still_counts_as_never_started(self):
        page1 = [self.annotation(message=self.BILLING, line=i) for i in range(p.ANNOTATIONS_PAGE_SIZE)]
        page2 = [self.annotation(message=self.BILLING, line=9001),
                 self.annotation(level="notice", message="label migration", line=9002)]
        with patch.object(p, "github_api", side_effect=[page1, page2]):
            self.assertTrue(p.never_started_billing_blocked(self.failing_run()))

    def test_annotation_pagination_403_fails_closed(self):
        for reason in ("github_http_403", "github_http_404"):
            with self.subTest(reason=reason), \
                 patch.object(p, "github_api", side_effect=p.Denied(reason)):
                with self.assertRaisesRegex(p.Denied, reason):
                    p.never_started_billing_blocked(self.failing_run())

    def test_annotation_malformed_or_non_list_page_fails_closed(self):
        cases = (("not-a-list", "check_annotations_unreadable"),
                 ([{"annotation_level": "failure"}], "check_annotations_malformed"),
                 ([{"message": None, "annotation_level": "failure"}], "check_annotations_malformed"),
                 ([self.annotation(), "raw-string"], "check_annotations_malformed"))
        for payload, reason in cases:
            with self.subTest(reason=reason), patch.object(p, "github_api", return_value=payload):
                with self.assertRaisesRegex(p.Denied, reason):
                    p._annotations(7)

    def test_annotation_partial_page_after_full_page_is_complete(self):
        page1 = [self.annotation(line=i) for i in range(p.ANNOTATIONS_PAGE_SIZE)]
        page2 = [self.annotation(line=9000)]
        with patch.object(p, "github_api", side_effect=[page1, page2]):
            self.assertEqual(len(p._annotations(7)), p.ANNOTATIONS_PAGE_SIZE + 1)

    def test_annotation_repeating_page_fails_closed(self):
        page = [self.annotation(line=i) for i in range(p.ANNOTATIONS_PAGE_SIZE)]
        with patch.object(p, "github_api", return_value=page):
            with self.assertRaisesRegex(p.Denied, "check_annotations_pagination_loop"):
                p._annotations(7)

    def test_annotation_overlapping_pages_fail_closed(self):
        first = [self.annotation(line=i) for i in range(p.ANNOTATIONS_PAGE_SIZE)]
        second = first[:-1] + [self.annotation(line=9100)]
        with patch.object(p, "github_api", side_effect=[first, second]):
            with self.assertRaisesRegex(p.Denied, "check_annotations_pagination_inconsistent"):
                p._annotations(7)

    def test_unbounded_annotation_pagination_fails_closed(self):
        counter = itertools.count()

        def fake(path):
            base = next(counter) * p.ANNOTATIONS_PAGE_SIZE
            return [self.annotation(line=base + i) for i in range(p.ANNOTATIONS_PAGE_SIZE)]

        with patch.object(p, "github_api", side_effect=fake):
            with self.assertRaisesRegex(p.Denied, "check_annotations_pagination_incomplete"):
                p._annotations(7)

    def test_pagination_query_is_allowlisted_but_arbitrary_queries_are_not(self):
        calls = []

        def fake_run(argv, timeout=30, allow_fail=False):
            calls.append(argv)
            return SimpleNamespace(stdout='{"http":200,"data":[]}', returncode=0)

        allowed = "/repos/" + p.REPO + "/check-runs/7/annotations?per_page=100&page=2"
        with patch.object(p, "run", side_effect=fake_run):
            self.assertEqual(p.github_api(allowed), [])
        rejected = (allowed + "&per_page=500",
                    "/repos/" + p.REPO + "/check-runs/7/annotations?per_page=100&page=abc",
                    "/repos/" + p.REPO + "/commits/" + SOURCE + "?per_page=100",
                    "/repos/" + p.REPO + "/check-runs/7/annotations?page=1")
        for path in rejected:
            with self.subTest(path=path):
                with self.assertRaisesRegex(p.Denied, "unsafe_github_resource"):
                    p.github_api(path)

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


    def test_pending_readback_recovers_only_exact_ref_without_redeploy(self):
        state = {"status": "readback_failed_rollback_required",
                 "pending_sha": NEW, "previous_sha": OLD, "release_prs": [42]}
        with patch.object(p, "read_state", return_value=state), \
             patch.object(p, "ref", side_effect=[NEW, NEW, NEW, NEW, NEW, NEW]), \
             patch.object(p, "live_release", side_effect=[OLD, OLD, NEW]), \
             patch.object(p, "candidate_history", side_effect=AssertionError("no re-admit")), \
             patch.object(p, "github_api", side_effect=AssertionError("no GitHub write")), \
             patch.object(p, "save") as save, \
             patch.object(p, "READBACK_INTERVAL", 0), \
             patch.object(p.time, "sleep") as sleep:
            result = p.process()
        self.assertEqual(result["result"], "deployed_after_retry")
        self.assertEqual(result["sha"], NEW)
        self.assertEqual(save.call_args[0][0]["release_prs"], [42])
        self.assertEqual(sleep.call_count, 1)

    def test_pending_plan_is_read_only_and_never_waits(self):
        state = {"status": "readback_failed_rollback_required", "pending_sha": NEW}
        with patch.object(p, "read_state", return_value=state), \
             patch.object(p, "ref", side_effect=[NEW, NEW, NEW, NEW]), \
             patch.object(p, "live_release", return_value=OLD), \
             patch.object(p, "github_api", side_effect=AssertionError("no writes")), \
             patch.object(p, "save", side_effect=AssertionError("no state write")), \
             patch.object(p.time, "sleep", side_effect=AssertionError("no waiting")):
            self.assertEqual(p.process(plan=True)["result"], "pending_readback")

    def test_pending_timeout_denies_without_rewind_or_state_mutation(self):
        state = {"status": "readback_failed_rollback_required", "pending_sha": NEW}
        with patch.object(p, "read_state", return_value=state), \
             patch.object(p, "ref", side_effect=[NEW, NEW, NEW, NEW]), \
             patch.object(p, "live_release", return_value=OLD), \
             patch.object(p, "READBACK_ATTEMPTS", 2), \
             patch.object(p.time, "sleep"), \
             patch.object(p, "github_api", side_effect=AssertionError("no writes")), \
             patch.object(p, "save", side_effect=AssertionError("no state mutation")):
            with self.assertRaisesRegex(p.Denied, "deployment_readback_failed_rollback_required"):
                p.process()

    def test_stale_pending_cannot_recover_another_sha(self):
        state = {"status": "readback_failed_rollback_required", "pending_sha": MID}
        with patch.object(p, "read_state", return_value=state), \
             patch.object(p, "ref", side_effect=[NEW, NEW]), \
             patch.object(p, "live_release", return_value=OLD), \
             patch.object(p, "github_api", side_effect=AssertionError("no writes")):
            with self.assertRaisesRegex(p.Denied, "production_not_at_current_release_ref"):
                p.process()

    def test_pending_race_after_success_never_records_deployment(self):
        state = {"status": "readback_failed_rollback_required", "pending_sha": NEW}
        with patch.object(p, "read_state", return_value=state), \
             patch.object(p, "ref", side_effect=[NEW, NEW, NEW, NEW, NEW, MID]), \
             patch.object(p, "live_release", side_effect=[OLD, NEW]), \
             patch.object(p, "save", side_effect=AssertionError("no state write")):
            with self.assertRaisesRegex(p.Denied, "git_ref_race"):
                p.process()

    def test_missing_pending_receipt_denies_stale_live(self):
        with patch.object(p, "read_state", return_value={}), \
             patch.object(p, "ref", side_effect=[NEW, NEW]), \
             patch.object(p, "live_release", return_value=OLD), \
             patch.object(p, "github_api", side_effect=AssertionError("no writes")):
            with self.assertRaisesRegex(p.Denied, "production_not_at_current_release_ref"):
                p.process()

    def test_untrusted_pending_receipt_is_rejected(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "target.json"
            target.write_text('{"status":"readback_failed_rollback_required"}')
            link = Path(root) / "receipt"
            link.symlink_to(target)
            with patch.object(p, "STATE", link):
                with self.assertRaisesRegex(p.Denied, "release_state_untrusted"):
                    p.read_state()
            with patch.object(p, "STATE", target):
                with self.assertRaisesRegex(p.Denied, "release_state_untrusted"):
                    p.read_state()

    def test_readback_window_bounded_by_systemd_timeout(self):
        self.assertEqual(p.READBACK_ATTEMPTS, 90)
        self.assertEqual(p.READBACK_INTERVAL, 10)
        self.assertLess(p.READBACK_ATTEMPTS * p.READBACK_INTERVAL, 20 * 60)

if __name__=="__main__":
    unittest.main()
