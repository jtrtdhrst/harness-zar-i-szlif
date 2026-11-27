# Kanoniczna segmentacja MCP, foldery Coolify i cykl Paperclip — decyzja 2026-10-22

**Status źródła:** GitHub `miloszspyrka-code/zar-i-szlif`, draft PR [#74](https://github.com/miloszspyrka-code/zar-i-szlif/pull/74). Repozytorium `main` pozostaje niezależne do zatwierdzenia przez CTO. **Ta strona odzwierciedla dokumentację `docs/architecture/monorepo-branches-and-deploy.md` z gałęzi PR #74**. Zapis w Wiki nie oznacza wdrożenia na VPS ani potwierdzenia konfiguracji Coolify.

---

# Architektura monorepo, segmentacja MCP i cykl wdrożeniowy — 2026-10-22

## Decyzja i stan faktyczny

**JEDNO repo:** `miloszspyrka-code/zar-i-szlif`. Jedyną gałęzią integracyjną/produkcyjną jest `main`. Gałęzie agentów to niezależne gałęzie robocze; bez autoryzowanego PR, testów i niezależnego review CTO nie mogą trafić na main. PR #74 jest **draft i źródłem zmian oczekujących na merge**, a nie aktualnym produkcyjnym `main`. Zamknięte PR #71 i #73 wymagające osobnego repo Harnessa są nieaktualne. Żadne zadanie nie upoważnia do zmiany modeli Paperclip ani kodu Paperclip/OpenCode Core.

**WYCOFANE:** `OpenDesign MCP` oraz `OpenCode MCP` — nie mają żadnej docelowej usługi Coolify, katalogu MCP ani aktywnej konfiguracji builda. Źródła zaimportowane poprzednio w `mcp/opendesign/`, `mcp/opencode/`, historyczny mostek `dev/integrations/opencode-mcp/` oraz build OpenDesign w legacy design-stack zostały usunięte z kandydata PR #74. Historia oryginalnych gałęzi GitHub nadal istnieje, ale nie podlega merge ani deployowi. **OpenCode jako runtime/model provider agentów pozostaje nienaruszony** (np. `opencode.json`); decyzja dotyczy wyłącznie nieużywanego dodatkowego MCP. Nie usuwać brandingu/UI produktu tylko dlatego, że nazwa katalogu lub opisy historycznie wspominają OpenDesign.

## Kanoniczne katalogi

```text
zar-i-szlif/
├── app/
│   ├── web/                  aplikacja produktu
│   ├── website/              publiczna strona produktu
│   ├── mcp-worker/           produktowy OAuth MCP / RAG
│   ├── cloudflare-worker/    API i OAuth produktu (inne niż MCP produktu)
│   └── plugin/               istniejący współdzielony kod produktu
├── mcp/
│   ├── mantic/               własny Mantic / Mautic MCP
│   ├── penpot/               własny Penpot MCP
│   ├── plasmic/              własny Plasmic MCP
│   ├── supabase/             hostowy konektor Supabase MCP
│   ├── ubuntu/               hostowy Ubuntu MCP
│   └── paperclip/            Paperclip MCP / gateway
├── supabase/                 schemat/migracje BAZY PRODUKTU; NIE Supabase MCP
├── ops/coolify/              manifest targetów, Dockerfile aplikacji
└── docs/architecture/       instrukcje i manifest gałęzi
```

Nie dopisywać ponownie katalogów `mcp/opendesign/` ani `mcp/opencode/`. Historyczne alternatywne wersje w `mcp/plasmic/_branches/` służą WYŁĄCZNIE do uzgadniania implementacji, nie do buildu ani deployu.

## Root budowania w Coolify — osobna usługa na każde wdrożenie

Wszystkie wybierają **TO SAMO** repo GitHub i **TYLKO zatwierdzone main**. `Base Directory` jest ustawieniem kontekstu aplikacji Coolify, nie mylić z folderem źródłowym.

| Usługa | Kod źródłowy | Coolify Base Directory | Dockerfile / kontekst | Port | Stan |
|---|---|---|---|---|---|
| Aplikacja produktu | `app/web/` | `/` | `ops/coolify/Dockerfile` / root `/` | 80 | plik builda istnieje |
| Strona WWW produktu | `app/website/` | `/` | `app/website/Dockerfile` / root `/` | 80 | build istnieje w PR #74; niezweryfikowany produkcyjnie |
| MCP produktu | `app/mcp-worker/` | brak gotowego Coolify | brak gotowego Dockerfile | — | **Cloudflare Worker obecnie; nie przenosić pozornie do Coolify** |
| Mantic MCP | `mcp/mantic/` | `/mcp/mantic` (planowane) | `mcp/mantic/Dockerfile` / `/mcp/mantic` | brak HTTP | Dockerfile stdio, wymagany wrapper HTTP i test |
| Penpot MCP | `mcp/penpot/` | `/mcp/penpot` (docelowo) | brak gotowego Dockerfile | — | źródła serwera niepełne |
| Plasmic MCP | `mcp/plasmic/` | `/mcp/plasmic` | `mcp/plasmic/Dockerfile.mcp` / `/mcp/plasmic` | 8091 | testy i obraz niezależny od wycofanego OpenDesign, wymagane live WAB E2E |
| Supabase MCP | `mcp/supabase/` | `/mcp/supabase` (docelowo) | brak gotowego Dockerfile | — | źródła konektora niepełne |
| Ubuntu MCP | `mcp/ubuntu/` | `/mcp/ubuntu` (docelowo) | brak gotowego Dockerfile | — | źródła konektora niepełne |
| Paperclip MCP | `mcp/paperclip/` | `/mcp/paperclip` (docelowo) | brak gotowego Dockerfile | — | częściowy kod gateway; niezależny runtime do potwierdzenia |

Źródło maszynowe: **`ops/coolify/targets.json`**. Manifest NIE jest dowodem konfiguracji uruchomionej w panelu Coolify. Każda usługa osobno konfiguruje repo/main, Dockerfile, kontekst, ścieżki wyzwalające jej build, zmienne środowiskowe, health, poświadczenia, port, domene, rollback i readback SHA/digest. Push do `main` nie ma automatycznie restartować wszystkich usług.

**Wyjątek MCP produktu:** kod `app/mcp-worker/src/index.ts` używa Cloudflare OAuthProvider, Workers KV i Workers AI; zwykły Node/Docker nie zapewnia równoważnego runtime. Jego przeniesienie do Coolify jest osobnym zadaniem z testami OAuth/security, nie efektem segmentacji folderów.

## Inwentaryzacja zmian i reguły AI merge

- **Mantic:** `KOMAA-1102` → aktywna kandydacka kopia `mcp/mantic/` (34 pliki). Nie mylić stdio z gotowym HTTP MCP.
- **Plasmic:** baseline `ops/design-stack` → `mcp/plasmic/`, wersje `KOMAA-1084` i `KOMAA-1174` w `_branches/`. Reconcile do aktywnego Plasmic po sprawdzeniu zmiany WAB 412, kontraktów, bezpieczeństwa i testów; nie scalać całej mieszanej gałęzi. OpenDesign usunięty z aktywnego obrazu i komponowania.
- **Penpot / Supabase MCP / Ubuntu MCP:** brak zweryfikowanego pełnego serwera w zaimportowanych gałęziach; importować jedynie z autoryzowanego źródła, ze sprawdzonym testem i bez sekretów.
- **Paperclip MCP:** częściowy bridge z `dev/integrations/paperclip-mcp/`; nie jest jeszcze pełną odtworzoną produkcją gateway/supervisor.
- **OpenDesign MCP / OpenCode MCP:** **wycofane**, oryginalne branże pozostają jedynie w historii. Kategorycznie nie dodawać do manifestu Coolify. Sam runtime OpenCode nie jest wycofany.
- **Wszystkie pozostałe gałęzie:** zinwentaryzowane z SHA w `docs/architecture/branch-inventory-20261022.json`. Nie importować niesprawdzonych gałęzi UI/produktowej bazy do hostowych `mcp/**`.

## Workflow Paperclip — jeden cykl, bez pozornych sukcesów

1. **COO/Harness klasyfikuje** zadanie do folderu i rzeczywistego właściciela, tworzy czytelne subtasks/Definition of Done po angielsku, prawdziwe zależności DAG i watchdog (agent nadrzędny, ewentualnie wykonawca). Nie dodawać sztucznego `blockedBy` dla watchdogów.
2. **Wykonawca** pobiera `main`, sprawdza `git remote`, `git status`, `git rev-parse --show-toplevel` i poprawny subtree; zmienia kod na izolowanej gałęzi `issue/<id>-<service>`, nie na `main`, nie w przypadkowym worktree lub repo innego projektu.
3. **Testy i dowody:** test kontraktu usługi, statyczne bezpieczeństwo, CI, docker build jeśli usługa jest gotowa, regresja rzeczywistego MCP i test negatywny; PR zapisuje dokładny kandydacki SHA i informację, co zmieniono. Brak runu/testu ≠ PASS.
4. **Review:** niezależny CTO lub wyznaczony recenzent podejmuje **rzeczywistą decyzję** w natywnych stage'ach Paperclip. Każdy kolejny commit wymaga nowego review SHA.
5. **Merge:** po decyzji zatwierdzającej i wymaganym CI PR trafia do wspólnego `main`. Żadna gałąź "agent-main" nie jest produkcyjnym refem. Ochrona GitHub main / wymagane kontrole musi być zweryfikowana; sam zapis w Wiki jej nie egzekwuje.
6. **Wdrożenie:** tylko właściwa aplikacja Coolify dostaje nową wersję `main` z odtwarzalnego SHA; ręczne/automatyczne powiadomienie odbywa się tylko dla pasujących folderów. Dla MCP produktu aktualne wydanie nadal osobną ścieżką Cloudflare, dopóki nie ma sprawdzonego adaptera.
7. **Readback + zamknięcie:** dokładny SHA, image digest, port/domain, uwierzytelnione `initialize` + `tools/list`, bezpieczna operacja canary, health/restart policy, rollback do poprzedniego SHA. Dopiero później Done w Paperclip i cleanup starych branchy po upewnieniu się, że żadna unikalna zmiana nie zginęła.

### Testy repo / CI
- `node scripts/check-coolify-targets.mjs`: katalogi, oddzielne targety, Dockerfile, zabezpieczenie przed budowaniem `_branches/`.
- `node scripts/check-retired-mcp.mjs`: nie istnieją wycofane foldery MCP, nie ma wycofanych serwisów w Compose/Dockerfile i nie naruszono `opencode.json`.
- `Monorepo MCP and website source CI`: walidacja, testy Mantic i Plasmic, obraz strony; zielone CI != wdrożenie na VPS.

**Nie zmieniono agentowych przypisań modeli.**


## Who gets which branch and workspace — execution routing (2026-10-22)

There is **one production/integration branch, main**, not a separate permanent "app branch", "MCP branch" or "Harness branch". Each agent works on a fresh isolated issue branch created from the correct repository's `origin/main`, with write paths gated by role. A new branch is required per issue. Old variant branches remain preserved as provenance, not default checkout.

| Owner | Default Paperclip project | Source root(s) permitted by default | Review / exception |
|---|---|---|---|
| Engineer | `01 · Produkt / Panel aplikacji` | `app/web/**`, product `app/cloudflare-worker/**`, `supabase/**`; website scope `app/website/**` in product website project | CTO independent reviewer |
| MCP Engineer | `02 · MCP / Product MCP` | `app/mcp-worker/**`; optional `app/plugin/knowledge/**` only with authorized task tools | CTO independent reviewer; NO infrastructure `mcp/**` |
| CTO | `01 · Produkt / Panel aplikacji` (review source) | Independent product reviewer by default; inspect other service branches only for assigned reviews | For CTO implementation use scope-specific workspace and COO/other independent reviewer |
| COO | Project/DAG dispatcher | No default code edits | Choose correct project/workspace, review participants, mandatory watchdog |

**Exact native issue fixes verified:** `KOMAA-1333`, `1336`, `1344`, `1337`, `1338`, `1339` now point to the product owner's `04 · Operations / Release & Reliability` project, project workspace `31b86f9a-0564-4f8b-af9c-7b5f9966471c`, and an isolated issue workspace strategy `git_worktree, baseRef=main, branchTemplate={{issue.identifier}}`. Their previous execution workspace bindings to upstream `paperclipai/paperclip/master` were cleared **without deleting the existing dirty upstream working tree**. `KOMAA-1084` Plasmic MCP was reassigned to Harness in that owner repo project; CTO remains reviewer, unique historic branch commit `ba42253985a28a154ee421d3008a50647abd91bb` retained.


**Preflight every execution:** Paperclip project ID + workspace ID must resolve to `https://github.com/miloszspyrka-code/zar-i-szlif`; read `git remote get-url origin`, `git branch --show-current`, `git status --porcelain`, `git rev-parse --show-toplevel`; fetch `origin/main`; ensure fresh issue branch and changed-file paths within role-owned service root. On mismatch preserve unmerged files/SHAs, reroute issue to owner project and new isolated workspace; never rewrite or delete other agents' changes. Before merge: scoped tests, independent native CTO approval of exact SHA, required GitHub checks, approved `main` merge. After merge: service-specific Coolify deployment with readback digest/health/tools-list/rollback. Staging PR #74 remains draft until review.


## Potwierdzone czyszczenie GitHub — 2026-10-22 (uzupełnienie po PR #74)

Po porównaniu z `origin/main`, sprawdzeniu otwartych PR oraz wykonaniu prawdziwych `git push origin --delete` usunięto siedem już włączonych do `main`, niepotrzebnych zdalnych refów: `chore/remove-vercel`, `docs/coolify-deployment-target`, `docs/coolify-github-app-source`, `feat/coolify-frontend-deployment`, `fix/first-registration-onboarding-guard-20261013`, `product/app`, `product/mcp`. Odczyt GitHub po operacji: **77 aktywnych gałęzi**; siedmiu wymienionych nazw brak. PR #57 (`KOMAA-1102`) został przestawiony z podstawy `product/mcp` na `main`, pozostaje draft. Nie zmieniono modeli, nie wdrożono usług i nie scalono PR #74.

W `docs/architecture/branch-inventory-20261022.json` na gałęzi PR #74 zachowano historyczne SHA 83-refowej migawki oraz dołożono zapis usuniętych refów, aktualny licznik i jedną nową gałąź nieobecną w migawce. **83 to historyczny licznik migawki, nie bieżący stan GitHub.** Pozostałe gałęzie z unikalnymi commitami, aktywnymi PR lub worktree wymagają osobnej weryfikacji przed kasowaniem.

Poprawki `README.md`, `AGENTS.md` i `.githooks/pre-push` są w **draft PR #74**, a nie w bieżącym `main`. Naprawa hooka eliminuje uruchamianie release-gate od niezwiązanego `HEAD` przy samym kasowaniu refów; testy zwykłego push i blokada bezpośredniego push na `main` pozostają wymagane. Pole **GitHub About / Description** i stare Homepage w ustawieniach repo to osobne metadane, których poprawy nie potwierdzono — sama zmiana README ich nie zmienia.
