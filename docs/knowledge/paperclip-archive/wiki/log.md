# Wiki Maintenance Log

## [2026-09-07] cleanup | durable context deduplication
- precedence: within the same source class, newer explicit material wins unless marked historical/superseded or delegating authority elsewhere.
- canonical agent contracts: only `wiki/agents/<role>/AGENTS.md`; removed duplicate `wiki/entities/agents-*` pages.
- removed non-durable or duplicate pages: executive standup/history snapshots, old Paperclip organization snapshots, old Worker runtime snapshot, Google Sheets tombstone, historical cycle mapping page, external-agent routing snapshot, `areas/knowledge`, and both `synthesis/*` pages.
- cleaned `wiki/index.md`, [[wiki/sources/wspolny-kontekst]], [[wiki/projects/kompas-zbiorek/decisions]], [[wiki/concepts/context-first-execution]], [[wiki/concepts/definition-of-done]], [[wiki/concepts/cykl-doskonalenia]], [[wiki/concepts/paperclip-wiki-mcp]], [[wiki/sources/baza-aktywnosci]] and affected agent contracts.
- rule: durable Wiki does not freeze CURRENT endpoint names, Worker names, tool names, deploy recipes, issue IDs or runtime availability unless the page is explicitly a current infrastructure contract.
- live control-plane alignment applied: `Kompas Product`, `Integrations & Release` and `Paperclip Ops` lead = CTO; `Growth & Onboarding` lead = CMO; COO remains top-level router rather than domain delivery lead.
- `Paperclip Ops` workspace policy corrected for its non-git `/app` `local_path`: default changed from `isolated_workspace + git_worktree` to serialized `shared_workspace + project_primary`, with issue override still allowed. This removes the invalid default that produced `git_worktree_base_not_git_checkout` on Paperclip Ops tasks.
- drained `Product UX & Accessibility` project moved from `in_progress` to `completed` after its only intended live issue K63 reached terminal `cancelled`; no new work should enter that project.
- remaining runtime mismatch: agent `capabilities` / permissions are still not fully synchronized with the new AGENTS contracts because the current MCP principal lacks `agents:configure` / `agents:suggest-changes`; do not treat stale capability text as canonical over `wiki/agents/<role>/AGENTS.md`.
- open ambiguity left unresolved: duplicate/pending MCP Engineer records in live runtime; canonical live UI URL used by Designer vs UI QA.

## [2026-09-04] sync + MCP CRUD
- canonical product cycle set to **Planowanie → Realizacja → Refleksja → Doskonalenie**.
- Google Sheets removed from product; Engineer deploys after required independent review.
- Wiki CRUD expanded to list/search/get/propose/apply/create/delete/move with optimistic locking; create→read→move→search→delete path verified.

## [2026-09-01] context architecture + data authority
- Supabase/Postgres established as the only application SSOT; Cloudflare Worker as API/integrations layer, not a second domain-data SSOT.
- introduced hierarchy of authority and role-based lazy loading instead of one huge context document.
- COO = default dispatcher; Engineer = scoped implementation; CTO = architecture/root-cause + independent technical review; UI QA = independent visual acceptance.
- frozen external API/runtime names no longer treated as eternal CURRENT.

## [2026-08-26] Paperclip MCP Wiki contract
- read-before-write, hash-based optimistic locking and path safety introduced for Wiki operations.

## [2026-08-20] initialization
- initialized Kompas Zbiórek LLM Wiki at `C:\Kompas Zbiórek\.paperclip-wiki`.
- consolidated durable product/agent knowledge from repo and prior context sources into the Wiki layer.

`wiki/log.md` is maintenance history only. It is not execution context and does not override [[wiki/sources/wspolny-kontekst]], current decisions or verified CURRENT.

## [2026-09-09] Wiki delete-page handler + 409 conflicts
- zarejestrowano brakujacy handler `delete-page` w workerze pluginu (usuwanie pliku + wierszy wiki_pages/revisions z hash-lockiem, pliki kontrolne index/log/WIKI/AGENTS/IDEA chronione).
- `paperclipWikiMovePage` dziala w calosci (copy + delete, bez duplikatow); `paperclipWikiDeletePage` zwraca status ok.
- konflikt starego hasha mapowany na HTTP 409 CONFLICT zamiast 502 WORKER_ERROR (obie trasy akcji).
- kontrakt create/read/move/update/delete ponownie prawdziwy i przetestowany end-to-end.

## [2026-09-29] mcp-qdrant — root cause narzedzi read/delete (KOMAA-407)
- `wiki/entities/mcp-qdrant-hybrid.md` += sekcja "Znane defekty narzedi" i "Zakres odpowiedzialnosci za kod vs runtime".
- zdiagnozowano, ze `get_document`/`delete_document` padaja dla kazdego argumentu (istniejacy, losowy UUID, smieci) przy stalym koszcie ~20 ms; `query` dziala.
- ustalono, ze pusta tresc bledu = `str(e) == ""` (format FastMCP ma `: {e}`, co potwierdza verbatimowy blad walidacji pydantic), a nie celowe sanowanie.
- fix wymaga wlasciciela hosta (obraz `mcp-qdrant-hybrid:latest`, klaster Qdrant Cloud poza `paperclip-net`) — egzekwowane przez child issue KOMAA-411; owner kontraktu/diagnostyki zostaje MCP Engineer.

## [2026-09-29] mcp-qdrant — root cause udowodnione + skorygowany wniosek o dostepie (KOMAA-411)
- `wiki/entities/mcp-qdrant-hybrid.md` += korekta sekcji "Zakres odpowiedzialnosci" i doprecyzowanie "Znanych defektow".
- **Sprostowany wniosek o dostepie:** serwer MCP jest osiagalny z runu agenta (`mcp-qdrant` -> `172.20.0.4`, `http://mcp-qdrant:8000/mcp`, streamable-http stateless). Wczesniejszy skan `172.17`-`172.20`/16 na `6333`/`6334` = 0 listenerow dotyczyl natywnego portu Qdrantu, nie MCP. Zablokowane bylo wdrrozenie, nie diagnoza.
- **`str(e) == ""` uzupelnione do dowodu:** FastMCP waliduje argumenty w tym samym `try` co handler i formatuje oba przypadki jedna linia `ToolError(f"Error executing tool {name}: {e}")`. Pusty komunikat przy obecnym `: {e}` w bledzie pydantic => wyjatek ma pusty `str()`. Zostaja dwie hipotezy (klasa bez instancji vs `StopIteration` z `next()`), rozroznialne wylacznie tracebackem w logu kontenera.
- nowe dane: awaria pada takze dla poprawnego `node_id` (dashed UUID) i pustego stringa; stalne ~20 ms ponad walidacja => jedno polaczenie do Qdrant zachodzi przed awaria; selekcja idzie filtrem po polu payload, nie przez `retrieve(point_ids=...)`.
- `unblockDescriptor.owner` nie pozwala agentowi wskazac board (403 "Agents may only name themselves as an unblock owner") — board trzeba wskazac przez interakcje z `resolverPolicy: human_only`.
- child issue dla wlasciciela hosta zostaje **unassigned**: Harness Agent tego nie odblokuje, bo zaden agent w firmie nie dosiega hosta.
- harness weryfikacyjny na kryteria 1-4 dodany do repo: `scripts/mcp-qdrant-verify.mjs` (commit `c9d1977`, `feature/rag-chatgpt-plugin`).

## [2026-10-05] control plane — responsible-user guard blokuje agentow (KOMAA-737)
- `wiki/entities/responsible-user-guard-outage.md` (nowa strona) — evidence + tabela zweryfikowanych 403.
- wszystkie endpointy API poza `GET /api/agents/me` zwracaja `RESPONSIBLE_USER_UNAVAILABLE`: listowanie issues/agents, activity, runs, bundle instrukcji (GET **i** PUT) oraz `POST /issues/{id}/comments`.
- guard siedzi w `server/src/middleware/auth.ts` (blad niezalezny od handlerow, pada na read i write); company rekord nie ma resolvable responsible user.
- objaw petli: run `f50028ff-e204-46f0-be7d-1fa3b120999c` spalil 30/30 tool calls na probowanie, zakonczyl `turn_budget_exhausted`, zero komentarzy → nastepny heartbeat budzi sie znów z `missing_issue_comment`.
- **nie** zmieniono `wiki/agents/ceo/AGENTS.md` z dysku: obchodzenie guarda poza kanoniczny PUT byloby samo w sobie naruszeniem granicy autoryzacji, a weryfikacja przez odczyt live bundle jest wlasnie zablokowana.
- owner odblokowania: wlasciciel auth middleware (read+write dla agent tokenow). Zmiana samej wlasnosci company to zmiana governance — wymaga osobnej aprobaty.

- 2026-10-20T22:46:24.163Z 2026-10-20 — Added `wiki/concepts/mascot-rework-ui-qa-rubric.md` (UI QA acceptance rubric for the post-rejection mascot rework): owner rejection of V4 SHA `2a092734` (KOMAA-1094, 21:42Z) recorded as a negative baseline; contrast acceptance re-anchored to the app's own surfaces (`app/web/src/styles.css` tokens, light theme only — the pipeline's `#16202E`/`#22405C` are proof-sheet backgrounds, not app surfaces) with the named element classes that fail (Szlif silhouette 1.01–1.74:1 and Iskra face ink 1.03–1.41:1 on the forest family; cream muzzle/raised paw 1.04–1.06:1 and Szlif eye 1.10–1.21:1 on paper) and the per-surface-family rule that one light rim cannot fix both; crop acceptance test (per-fill cut test, per-column run test, widening trap); per-size proof expectations; stdlib-only reproduction method; verified chrome-devtools environment notes (browser runs in a separate container — bind `0.0.0.0` and use the container IP; screenshots with `filePath` land in the browser container; blocker `browser_runtime_absent_libglib2.0` is RESOLVED); and the platform gap where agent comment/status writes are refused with `403 cross_issue_influence_run_context_required` while issue document writes succeed, so verdicts must be carried in issue documents. Wiki index updated to link the new page and the previously unindexed `wiki/concepts/mascot-style-2-pipeline`. Source evidence: KOMAA-1095 documents `qa-evidence-v4-app-surface-contrast`, `qa-evidence-v4-optical-cut-plane`, `qa-rubric-delivery-note`.
