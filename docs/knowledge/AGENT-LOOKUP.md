# Repowise agent lookup contract

- Private endpoint: `http://repowise-mcp:7338/mcp` in the Coolify internal network; requires bearer authentication.
- First call `list_repos`, confirm distinct aliases `product` and `harness` and indexed commit SHA.
- Use `get_context`, `search_codebase`, `get_why` and `get_change_risk` for target code and decisions.
- Use `get_blast_radius` and `get_architecture` for multi-repo impact, but inspect evidence; generic route matches `/health` or OAuth discovery **do not prove** a dependency.
- Validate against actual GitHub, service configuration and Coolify readback; never assume an open PR is indexed `main`.
- Only trust historical Paperclip pages as provenance, not active Multica role instructions.

## Backend architecture reference — authoritative dated snapshot

- Canonical complete snapshot: `docs/architecture/BACKEND-ARCHITECTURE-2026-11-09.md` in `harness` (731 lines / 16 chapters). Includes product backend, MCP, OAuth, Supabase/Qdrant, Multica, Hermes, Paperclip, Hindsight, Opik, Docker, Coolify, security, E2E evidence and gaps.
- Native RepoWise E2E retrieval: `list_repos` → `search_codebase(repo="harness",mode="path",query="BACKEND-ARCHITECTURE-2026-11-09.md")` → `get_context(repo="harness",targets=["docs/architecture/BACKEND-ARCHITECTURE-2026-11-09.md"])` → `get_symbol(repo="harness",symbol_id="docs/architecture/BACKEND-ARCHITECTURE-2026-11-09.md:1-80")`. Continue with subsequent line ranges for the relevant chapter; the source-range read is verified against the indexed live file.
- If `get_answer` reports `no-llm-provider` or `search_codebase` concept retrieval ranks unrelated code, **do not fabricate a synthesis**. Discover the document by exact path and retrieve its line ranges. Semantic retrieval is disabled with the current mock embedder.
- Snapshot claims are graded `LIVE`, `SOURCE`, `DOC`, `PARTIAL`, `OPEN`; the document is **not a release gate** or proof of current production state. For runtime changes, recheck actual GitHub SHA, running image digest and active API/DB configuration.
- Preserve repository boundaries: app code is owned by `product`, platform and infrastructure by `harness`; the central document lives in `harness` to avoid duplicating conflicting versions. Never use archived Paperclip instructions as active Multica policy.
