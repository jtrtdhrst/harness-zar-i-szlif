"""Regression checks for RepoWise branch/build retrieval in the pinned 0.60.1 wheel."""
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from pathlib import Path
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
        for question in (
            "Która gałąź buduje github-ops-mcp?",
            "Z jakiej gałęzi budowany jest github-ops-mcp?",
            "Który branch buduje github-ops-mcp?",
            "Jaka jest produkcyjna gałąź github-ops-mcp?",
        ):
            self.assertTrue(a._branch_source_question(question), question)
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


    async def test_two_real_repo_roots_isolated(self):
        """Harness-only branch row must never appear when product is selected."""
        with TemporaryDirectory() as tmp:
            roots = {name: Path(tmp) / name for name in ("harness", "product")}
            for root in roots.values():
                folder = root / "ops" / "repowise"
                folder.mkdir(parents=True)
            (roots["harness"] / "ops/repowise/BRANCH_BUILD_PROVENANCE.md").write_text(
                "# Verified build source\n" + row() + "\n", encoding="utf-8"
            )
            (roots["product"] / "ops/repowise/README.md").write_text(
                "# Product build instructions\nNo github-ops-mcp branch entry.\n", encoding="utf-8"
            )
            calls = []

            async def local_source_search(*, query, limit, mode, repo):
                self.assertIn(repo, roots)
                calls.append(repo)
                name = query.strip(chr(96))
                lines = []
                for source in (roots[repo] / "ops/repowise").glob("*.md"):
                    for number, content in enumerate(
                        source.read_text(encoding="utf-8").splitlines(), start=1
                    ):
                        if name in content:
                            lines.append({
                                "path": str(source.relative_to(roots[repo])),
                                "line": number, "text": content,
                            })
                return {"lines": lines}

            with patch(
                "repowise.server.mcp_server.tool_search.tool.search_codebase",
                new=local_source_search,
            ), patch.object(
                a, "filter_dicts_by_key", side_effect=lambda hits, key, spec: hits
            ):
                harness_hits = await a._literal_source_anchor_hits(
                    "Which branch builds github-ops-mcp?",
                    repo_alias="harness", scope=None, exclude_spec=None,
                )
                product_hits = await a._literal_source_anchor_hits(
                    "Which branch builds github-ops-mcp?",
                    repo_alias="product", scope=None, exclude_spec=None,
                )
            self.assertEqual(calls, ["harness", "product"])
            self.assertEqual(len(harness_hits), 1)
            self.assertEqual(product_hits, [])
            self.assertIn("feat/github-ops-mcp-20261120", harness_hits[0]["excerpt"])

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


class LiveMarkdownEvidenceTests(unittest.TestCase):
    def test_missing_wiki_body_is_replaced_by_verified_source_lines(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "ops" / "repowise" / "BRANCH_BUILD_PROVENANCE.md"
            p.parent.mkdir(parents=True)
            p.write_text("# Branch provenance\n" + row() + "\n")
            h = {"target_path": str(p.relative_to(tmp)), "page_type": "file_page"}
            excerpt = a._verified_markdown_source_excerpt(
                h, Path(tmp), "Which configured branch builds github-ops-mcp?"
            )
            self.assertIsNotNone(excerpt)
            self.assertIn("feat/github-ops-mcp-20261120", excerpt)
            self.assertIn("L2:", excerpt)

    def test_no_source_fabrication_for_missing_or_unrelated_docs(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "doc.md"
            p.write_text("# Fruit growing\nOranges and lemons.\n")
            for path in ["missing.md", "../doc.md", "/etc/passwd", "doc.md"]:
                h = {"target_path": path}
                self.assertIsNone(a._verified_markdown_source_excerpt(
                    h, Path(tmp), "Which branch builds github-ops-mcp?"
                ))

    def test_source_symlinks_are_refused(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "src.md"
            p.write_text(row())
            (Path(tmp) / "link.md").symlink_to(p)
            h = {"target_path": "link.md"}
            self.assertIsNone(a._verified_markdown_source_excerpt(
                h, Path(tmp), "Which branch builds github-ops-mcp?"
            ))




class CacheFreshnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_branch_answer_bypasses_stale_cache_and_rechecks_current_evidence(self):
        """Even a pre-existing stale answer cannot override a newer branch mapping."""
        @asynccontextmanager
        async def session(_factory):
            yield object()

        context = SimpleNamespace(path=Path("."), session_factory=lambda: None)
        repo = SimpleNamespace(id="harness", name="harness")
        first = hit("github-ops-mcp", "feat/old")
        second = hit("github-ops-mcp", "feat/new")
        evidence = [
            a._Retrieved([h], [h], set(), {}, [])
            for h in (first, second)
        ]
        with patch.object(a, "_resolve_repo_context", new=AsyncMock(return_value=context)), \
             patch.object(a, "_get_exclude_spec", return_value=None), \
             patch.object(a, "get_session", new=session), \
             patch.object(a, "_get_repo", new=AsyncMock(return_value=repo)), \
             patch.object(a, "_data_shape_answer", new=AsyncMock(return_value=None)), \
             patch.object(a, "_cache_disabled", return_value=False), \
             patch.object(a, "_serve_cached_answer", new_callable=AsyncMock,
                          return_value={"answer": "STALE"}) as cached, \
             patch.object(a, "_run_retrieval_pipeline", new_callable=AsyncMock,
                          side_effect=evidence) as search, \
             patch.object(a, "_with_candidates", side_effect=lambda payload, pool: payload):
            results = [
                await a._get_answer_raw("Which branch builds github-ops-mcp?", repo="harness")
                for _ in range(2)
            ]
        self.assertIn("feat/old", results[0]["answer"])
        self.assertIn("feat/new", results[1]["answer"])
        self.assertNotIn("feat/old", results[1]["answer"])
        self.assertEqual(search.await_count, 2)
        cached.assert_not_awaited()

    async def test_unrelated_question_keeps_normal_cache_path(self):
        @asynccontextmanager
        async def session(_factory):
            yield object()

        context = SimpleNamespace(path=Path("."), session_factory=lambda: None)
        repo = SimpleNamespace(id="harness", name="harness")
        with patch.object(a, "_resolve_repo_context", new=AsyncMock(return_value=context)), \
             patch.object(a, "_get_exclude_spec", return_value=None), \
             patch.object(a, "get_session", new=session), \
             patch.object(a, "_get_repo", new=AsyncMock(return_value=repo)), \
             patch.object(a, "_data_shape_answer", new=AsyncMock(return_value=None)), \
             patch.object(a, "_cache_disabled", return_value=False), \
             patch.object(a, "_serve_cached_answer", new_callable=AsyncMock,
                          return_value={"answer": "CACHED"}) as cached, \
             patch.object(a, "_run_retrieval_pipeline", new_callable=AsyncMock) as search:
            result = await a._get_answer_raw(
                "Explain github-ops-mcp architecture", repo="harness"
            )
        self.assertEqual(result["answer"], "CACHED")
        cached.assert_awaited_once()
        search.assert_not_awaited()



if __name__ == "__main__":
    unittest.main()
