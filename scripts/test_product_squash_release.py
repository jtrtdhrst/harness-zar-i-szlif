"""Fail-closed regression tests for exact PR-bound squash and docs-only no-op."""
import os
import tempfile
import unittest
from unittest.mock import patch
import product_native_promotion as p

OLD = "a" * 40
NEW = "b" * 40
MID = "c" * 40
HEAD = "d" * 40

class ProductSquashTests(unittest.TestCase):
    def test_known_knowledge_squash_skips_release_and_ref_write(self):
        sha=p.LEGACY_KNOWLEDGE_SHA
        node={"sha":sha,"parents":[{"sha":OLD}],"files":[
            {"filename":"docs/knowledge/README.md","status":"added"},
            {"filename":".repowise/decisions.yaml","status":"added"},
            {"filename":"scripts/ci-path-coverage.mjs","status":"modified"},
            {"filename":"tests/ci-path-coverage.test.mjs","status":"modified"}]}
        with patch.object(p,"ref",side_effect=[sha,OLD]), \
             patch.object(p,"live_release",return_value=OLD), \
             patch.object(p,"commit",return_value=node), \
             patch.object(p,"provenance",return_value=(164,HEAD)), \
             patch.object(p,"checks",return_value={"billing_blocked":False}) as checks, \
             patch.object(p,"native_approval",side_effect=AssertionError("never review doc-only")):
            result=p.process(plan=False)
        self.assertEqual(result["result"],"no_runtime_release_required")
        self.assertEqual(result["live"],OLD)
        self.assertEqual(result["release_ref"],OLD)
        self.assertEqual(checks.call_count,2)

    def test_single_parent_direct_push_rejected(self):
        node={"sha":NEW,"parents":[{"sha":OLD}],"files":[{"filename":"docs/a.md","status":"modified"}]}
        with patch.object(p,"commit",return_value=node), \
             patch.object(p,"provenance",side_effect=p.Denied("missing_or_ambiguous_main_pr")):
            with self.assertRaisesRegex(p.Denied,"missing_or_ambiguous_main_pr"):
                p.candidate_history(OLD,NEW)

    def test_docs_checks_required_even_without_native_review(self):
        node={"sha":NEW,"parents":[{"sha":OLD}],"files":[{"filename":"docs/a.md","status":"modified"}]}
        with patch.object(p,"commit",return_value=node), \
             patch.object(p,"provenance",return_value=(167,HEAD)), \
             patch.object(p,"checks",side_effect=p.Denied("product_ci_not_green")):
            with self.assertRaisesRegex(p.Denied,"product_ci_not_green"):
                p.candidate_history(OLD,NEW)

    def test_runtime_squash_requires_native_approval(self):
        node={"sha":NEW,"parents":[{"sha":OLD}],"files":[{"filename":"app/web/src/index.ts","status":"modified"}]}
        with patch.object(p,"commit",return_value=node), \
             patch.object(p,"provenance",return_value=(167,HEAD)), \
             patch.object(p,"checks",return_value={"billing_blocked":False}) as checks, \
             patch.object(p,"native_approval",side_effect=p.Denied("native_approval_unverified")):
            with self.assertRaisesRegex(p.Denied,"native_approval_unverified"):
                p.candidate_history(OLD,NEW)
            self.assertEqual(checks.call_count,2)

    def test_legacy_exception_is_sha_and_pr_specific(self):
        node={"files":[{"filename":"scripts/ci-path-coverage.mjs","status":"modified"}]}
        self.assertTrue(p.non_runtime_files_only(164,p.LEGACY_KNOWLEDGE_SHA,node))
        for pr,sha in [(164,NEW),(166,p.LEGACY_KNOWLEDGE_SHA),(166,NEW)]:
            self.assertFalse(p.non_runtime_files_only(pr,sha,node))
        self.assertFalse(p.non_runtime_files_only(166,NEW,{"files":[{"filename":"app/index.ts","status":"modified"}]}))
        self.assertFalse(p.non_runtime_files_only(166,NEW,{"files":[{"filename":"docs/a.md","status":"renamed","previous_filename":"app/a.js"}]}))
        with self.assertRaisesRegex(p.Denied,"commit_file_inventory"):
            p.non_runtime_files_only(166,NEW,{"files":[]})

    def test_mixed_history_docs_skipped_runtime_reviewed(self):
        docs={"sha":MID,"parents":[{"sha":OLD}],"files":[{"filename":"docs/index.md","status":"modified"}]}
        runtime={"sha":NEW,"parents":[{"sha":MID}],"files":[{"filename":"app/src.ts","status":"modified"}]}
        with patch.object(p,"commit",side_effect=lambda sha:{MID:docs,NEW:runtime}[sha]), \
             patch.object(p,"provenance",side_effect=lambda sha:(169,HEAD) if sha==NEW else (168,HEAD)), \
             patch.object(p,"checks",return_value={"billing_blocked":False}) as checks, \
             patch.object(p,"native_approval") as native:
            result=p.candidate_history(OLD,NEW)
        self.assertEqual([x["pr"] for x in result],[169])
        native.assert_called_once_with(169,HEAD,NEW)
        self.assertEqual(checks.call_count,4)

    def test_billing_block_without_root_attestation_denies_before_any_ref_write(self):
        """A billing-blocked CI run is never released without root-attested evidence.

        `checks()` reports the account billing block, so the controller must fall
        back to the root-owned local-CI attestation of the reviewed head. With the
        real reader pointed at an empty attestation tree - no file, so no root-owned
        evidence - it must deny and must not touch the release ref or ask for a review.
        """
        node = {"sha": NEW, "parents": [{"sha": OLD}],
                "files": [{"filename": "app/web/src/index.ts", "status": "modified"}],
                "commit": {"tree": {"sha": "t" * 40}}}
        head = {"sha": HEAD, "commit": {"tree": {"sha": "t" * 40}}}
        with tempfile.TemporaryDirectory() as empty, \
             patch.object(p, "LOCAL_CI_DIR", p.Path(empty)), \
             patch.object(p, "ATTESTATION_UID", os.getuid()), \
             patch.object(p, "ATTESTATION_GID", os.getgid()), \
             patch.object(p, "ref", side_effect=[NEW, OLD]), \
             patch.object(p, "live_release", return_value=OLD), \
             patch.object(p, "commit", side_effect=lambda sha: {NEW: node, HEAD: head}[sha]), \
             patch.object(p, "provenance", return_value=(169, HEAD)), \
             patch.object(p, "checks", return_value={"billing_blocked": True}), \
             patch.object(p, "github_api", side_effect=AssertionError("no GitHub write")), \
             patch.object(p, "native_approval", side_effect=AssertionError("must not be reached")):
            with self.assertRaisesRegex(p.Denied, "local_ci_attestation_missing"):
                p.process(plan=False)


    def test_exact_reviewed_ci_pr183_skips_runtime_release_only_with_strong_proof(self):
        files=[{"filename":name,"status":status}
               for name,status in p.CI_ONLY_REVIEWED_FILES.items()]
        node={"sha":NEW,"parents":[{"sha":OLD}],"files":files}
        self.assertTrue(p.reviewed_ci_only_pr(183,p.CI_ONLY_REVIEWED_HEAD,node))
        with patch.object(p,"ref",side_effect=[NEW,OLD]), \
             patch.object(p,"live_release",return_value=OLD), \
             patch.object(p,"commit",return_value=node), \
             patch.object(p,"provenance",return_value=(183,p.CI_ONLY_REVIEWED_HEAD)), \
             patch.object(p,"premerge_head_checks",return_value={"rootless_premerge":True,"billing_blocked":False}), \
             patch.object(p,"checks",return_value={"billing_blocked":False}), \
             patch.object(p,"native_approval",side_effect=AssertionError("CI-only cannot become runtime")), \
             patch.object(p,"github_api",side_effect=AssertionError("no GitHub ref write")):
            result=p.process(plan=False)
        self.assertEqual(result["result"],"no_runtime_release_required")
        self.assertEqual(result["release_ref"],OLD)

    def test_ci_only_exception_rejects_other_sha_pr_files_and_renames(self):
        base=[{"filename":name,"status":status}
              for name,status in p.CI_ONLY_REVIEWED_FILES.items()]
        node={"files":base}
        self.assertFalse(p.reviewed_ci_only_pr(184,p.CI_ONLY_REVIEWED_HEAD,node))
        self.assertFalse(p.reviewed_ci_only_pr(183,HEAD,node))
        self.assertFalse(p.reviewed_ci_only_pr(183,"387e5f9081fa9fa9da4820fae054da617c615a9a",node))
        self.assertFalse(p.reviewed_ci_only_pr(183,p.CI_ONLY_REVIEWED_HEAD,
                           {"files":base+[{"filename":"app/web/src/index.ts","status":"modified"}]}))
        self.assertFalse(p.reviewed_ci_only_pr(183,p.CI_ONLY_REVIEWED_HEAD,
                           {"files":base[:-1]}))
        altered=[dict(x) for x in base]
        altered[0]["status"]="renamed"
        self.assertFalse(p.reviewed_ci_only_pr(183,p.CI_ONLY_REVIEWED_HEAD,
                           {"files":altered}))
        self.assertFalse(p.reviewed_ci_only_pr(183,p.CI_ONLY_REVIEWED_HEAD,
                           {"files":base+[base[0]]}))

    def test_ci_only_exception_requires_rootless_proof_and_green_main(self):
        node={"sha":NEW,"parents":[{"sha":OLD}],"files":[
            {"filename":name,"status":status}
            for name,status in p.CI_ONLY_REVIEWED_FILES.items()]}
        for receipt,main_billed in ((False,False),(True,True)):
            with self.subTest(rootless=receipt,main_billed=main_billed), \
                 patch.object(p,"commit",return_value=node), \
                 patch.object(p,"provenance",return_value=(183,p.CI_ONLY_REVIEWED_HEAD)), \
                 patch.object(p,"premerge_head_checks",return_value={"rootless_premerge":receipt,"billing_blocked":False}), \
                 patch.object(p,"checks",return_value={"billing_blocked":main_billed}), \
                 patch.object(p,"native_approval",side_effect=AssertionError("must deny before runtime")):
                with self.assertRaisesRegex(p.Denied,"ci_only_rootless_proof_or_main_ci_missing"):
                    p.candidate_history(OLD,NEW)


    def test_native_product_ci_never_runs_untrusted_pr_on_persistent_runner(self):
        from pathlib import Path
        workflow=(Path(__file__).resolve().parent.parent /
                  ".github/workflows/native-product-release-ci.yml").read_text()
        self.assertIn("if: github.event_name == 'push' && github.ref == 'refs/heads/main'",workflow)
        self.assertIn("runs-on: [self-hosted, linux, x64, local-build]",workflow)
        self.assertIn("test \"$(id -un)\" = actions-zis",workflow)
        self.assertIn("! test -w /var/run/docker.sock",workflow)
        self.assertIn("persist-credentials: false",workflow)
        self.assertIn("test_product_squash_release.py -v",workflow)
        self.assertNotIn("  pull_request:",workflow)
        self.assertNotIn("  pull_request_target:",workflow)
        self.assertNotIn("runs-on: ubuntu-latest",workflow)

if __name__=="__main__":
    unittest.main()
