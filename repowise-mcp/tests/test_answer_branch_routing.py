"""Regression checks for RepoWise branch/build retrieval in the pinned 0.60.1 wheel."""
import unittest
from unittest.mock import AsyncMock, patch

from repowise.server.mcp_server.tool_answer import answer as a


def row(name="github-ops-mcp", branch="feat/github-ops-mcp-20261120"):
    q = chr(96)
    return f"| {q}{name}{q} / {q}t09dqe2eppn2eiqmhzlf8xzp{q} | {q}miloszspyrka-code/harness-zar-i-szlif{q} | {q}{branch}{q} | manual HOLD"


def hit(name, branch, path="ops/repowise/BRANCH_BUILD_PROVENANCE.md"):
    raw = row(name, branch)
    return {
        "target_path": path, "_sources": {"literal"},
        "snippet": f"Verified source line 20: {raw}",
        "page_type": "file",
    }


class IdentifierTests(unittest.TestCase):
    def test_only_explicit_service_identifiers(self):
        question = "Which branch builds github-ops-mcp and zar-i-szlif-web?"
        self.assertEqual(a._service_identifiers(question), ["github-ops-mcp", "zar-i-szlif-web"])
        self.assertTrue(a._branch_source_question(question))
        self.assertFalse(a._branch_source_question("Explain github-ops-mcp architecture"))
        self.assertEqual(a._service_identifiers("plain words without service names"), [])

    def test_exact_config_and_dated_runtime_disclaimer(self):
        one = hit("github-ops-mcp", "feat/github-ops-mcp-20261120")
        two = hit("zar-i-szlif-web", "ci-approved")
        r = a._Retrieved([one, two], [one, two], set(), {}, [])
        out = a._exact_config_answer("Which branches build github-ops-mcp and zar-i-szlif-web?", r)
        self.assertIn("feat/github-ops-mcp-20261120", out["answer"])
        self.assertIn("ci-approved", out["answer"])
        self.assertIn("NOT proof", out["answer"])
        self.assertEqual(out["confidence"], "medium")
        self.assertEqual(out["citations"], ["ops/repowise/BRANCH_BUILD_PROVENANCE.md"])

    def test_no_fabricated_branch_from_malformed_row(self):
        malformed = {
            "target_path": "ops/repowise/BRANCH_BUILD_PROVENANCE.md",
            "_sources": {"literal"},
            "snippet": "Verified source line 7: github-ops-mcp is deployed from main",
        }
        r = a._Retrieved([malformed], [malformed], set(), {}, [])
        self.assertIsNone(a._exact_config_answer("Which branch builds github-ops-mcp?", r))
        self.assertIsNone(a._exact_config_answer("What does github-ops-mcp do?", r))

    def test_no_cross_repo_synthesis_from_empty_evidence(self):
        r = a._Retrieved([], [], set(), {}, [])
        self.assertIsNone(a._exact_config_answer("Which branch builds github-ops-mcp?", r))


class AnchorTests(unittest.IsolatedAsyncioTestCase):
    async def test_prefers_exact_row_over_alphabetically_earlier_decoy(self):
        name = "zar-i-szlif-web"
        decoy = {"path": "docs/architecture/BACKEND.md", "line": 5,
                 "text": f"| other service | {name} | uncertain |"}
        exact = {"path": "ops/repowise/BRANCH_BUILD_PROVENANCE.md", "line": 20,
                 "text": row(name, "ci-approved")}
        q = chr(96) + name + chr(96)
        with patch("repowise.server.mcp_server.tool_search.tool.search_codebase",
                   new_callable=AsyncMock, return_value={"lines": [decoy, exact]}) as search:
            with patch.object(a, "filter_dicts_by_key", side_effect=lambda hits, key, spec: hits):
                hits = await a._literal_source_anchor_hits(
                    "Which branch builds zar-i-szlif-web?",
                    repo_alias="harness", scope=None, exclude_spec=None,
                )
        search.assert_awaited_once_with(query=q, limit=10, mode="hybrid", repo="harness")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["target_path"], exact["path"])
        self.assertIn("ci-approved", hits[0]["excerpt"])

    async def test_scope_is_respected_without_exception(self):
        exact = {"path": "ops/repowise/BRANCH_BUILD_PROVENANCE.md",
                 "line": 23, "text": row()}
        with patch("repowise.server.mcp_server.tool_search.tool.search_codebase",
                   new_callable=AsyncMock, return_value={"lines": [exact]}):
            with patch.object(a, "filter_dicts_by_key", side_effect=lambda hits, key, spec: hits):
                hits = await a._literal_source_anchor_hits(
                    "Which branch builds github-ops-mcp?", repo_alias="product",
                    scope="app/", exclude_spec=None,
                )
        self.assertEqual(hits, [])

    async def test_absent_source_does_not_invent_branch(self):
        with patch("repowise.server.mcp_server.tool_search.tool.search_codebase",
                   new_callable=AsyncMock, return_value={"lines": []}):
            with patch.object(a, "filter_dicts_by_key", side_effect=lambda hits, key, spec: hits):
                hits = await a._literal_source_anchor_hits(
                    "Which branch builds github-ops-mcp?",
                    repo_alias="harness", scope=None, exclude_spec=None,
                )
        self.assertEqual(hits, [])

    async def test_unrelated_question_does_not_query_search(self):
        with patch("repowise.server.mcp_server.tool_search.tool.search_codebase",
                   new_callable=AsyncMock) as search:
            hits = await a._literal_source_anchor_hits(
                "Explain github-ops-mcp architecture",
                repo_alias="harness", scope=None, exclude_spec=None,
            )
        self.assertEqual(hits, [])
        search.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
