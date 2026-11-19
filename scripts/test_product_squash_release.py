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

if __name__=="__main__":
    unittest.main()
