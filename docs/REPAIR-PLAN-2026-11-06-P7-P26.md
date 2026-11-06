# Plan naprawczy P7–P26 — Żar i Szlif / Paperclip / Hermes / Opik

Data: 2026-11-06
Zakres: P7–P26 z audytu produkcyjnego. Dokument jest planem wykonawczym, nie deklaracją DONE.
Zasada: każda pozycja ma dowód, właściciela, test akceptacyjny i rollback. Pozycje oznaczone
`FIXED` zostały zweryfikowane w tym przebiegu; `OPEN` wymagają wdrożenia; `MISDIAGNOSED`
oznacza, że opis w audycie nie odpowiada rzeczywistemu mechanizmowi.

## 0. Streszczenie

Realnie naprawione teraz:

- **P8** — kontroler promocji miał zbyt krótkie okno readback (4 min) i po timeoucie blokował
  kolejne przebiegi. Zwiększono okno do 15 min, dodano wznowienie oczekującego wdrożenia,
  podniesiono `TimeoutStartSec` do 20 min, timer jest aktywny. Testy 19/19, live `--plan`
  zwraca `already_released` dla `98cd058…`.
- **P9/P12** — Hindsight Designera nie używał self-hosted, bo plugin czytał launch-scope
  `/opt/data/hindsight/config.json` (`mode=cloud`, SaaS), a nie profilowy
  `/opt/data/profiles/designer/hindsight/config.json` (`local_external`). Poprawiono resolver
  w 15 kopiach pluginu; 14/14 profili ładuje własny bank i endpoint MCP. Retain/recall
  potwierdzony dla faktów operacyjnych (5 faktów, recall zwraca „Designer używa DeepSeek
  przez opencode-go”); syntetyczny canary był odfiltrowany przez ekstraktor (0 faktów).
- **P7 (część harness)** — `docs/RELEASE-POLICY.md` nadal opisywał usunięty `promote-release`;
  poprawiono w tym PR. Produktowy PR #153 nadal wymaga review (patrz P7).

Najważniejsze otwarte blokery:

- **P11/P14** — Hermes widzi 248 narzędzi, ale `mcp_paperclip__*` kończy się
  „Tool not found”; są dwa aktywne połączenia Paperclip MCP o tym samym URL
  (general + dedicated) i podwójny katalog. 13/14 agentów nadal na `opencode_local`.
- **P13** — produkcyjny Hermes działa z HEAD otwartego PR #74; CTO dał
  `CHANGES_REQUESTED` za współdzielony stan narzędzi, poprawka `81fa3ae` czeka na re-review.
- **P17/P18** — wewnętrzny odczyt Opik przez MCP naprawiony (`:8081`, 16 projektów);
  publiczny OAuth i pełny trace pozostają do potwierdzenia.
- **P25/P26** — push z runu **działa** (PR #158), ale runy raportują `githubAuthenticationMode=host`,
  brak managed identity, a autor commita to bot `miloszspyrka-code`, nie tożsamość agenta.
  CTO ma dodatkowo per-agent override `!gh auth git-credential`, który w kontenerze bez
  `gh` zawodzi.
- **P23** — izolacja banków Hindsight działa w Caddy, ale core `:8888` ufa każdemu
  klientowi w swojej sieci Docker (bez auth). Port nie jest publiczny; to luka wewnętrzna,
  nie wystawienie na Internet. Brak backupu wolumenu DB.
- **P7 (produkt)** — PR #153 jest gotowy, ale nie może wejść bez natywnej akceptacji, bo
  kontroler P8 weryfikuje **każdy** merge na `main`.

Pozycje przeklasyfikowane po debugu:

- **P15** — to nie jest rozjazd konfiguracji etapu z runtime. Oba issues mają
  `changesRequestedCount=3`, czyli osiągnęły limit rund i zostały **celowo** przekazane
  człowiekowi (`responsibleUserId`). Runtime jest zgodny z kontraktem eskalacji.
- **P16** — 748 akcji/929 runów w niepełnym tygodniu to nie „77% nieudanych runów”.
  Dominuje jednorazowy backfill `legacy_execution_requires_reconciliation` (562 akcji,
  głównie 2026-11-03). Metryka wymaga rozdzielenia backfillu od bieżących awarii.

## 1. Metodyka i dowody

- VPS: `ssh -i /root/.config/opencode/ubuntu-mcp/harness-ops harness-ops@51.89.174.58`,
  polecenia przez `sudo`.
- Systemd: `systemctl cat/status`, `journalctl -u product-native-promotion.service`.
- Paperclip: `db-2omzqpy8dxgmhuwfbzo7bvvv` (`psql -U paperclip -d paperclip`) oraz API
  `http://127.0.0.1:3100/api` z board key.
- Hermes: `docker exec 2sganhxhhnioiqh4an9g2f4k`, logi `/opt/data/logs/agent.log`,
  profile `/opt/data/profiles/*`.
- Hindsight: `hindsight-hjda7ckq5z4luhd1vpdepi0r` + `hindsight-mcp-aglen8ervlo2lpi30oz8iii9`.
- Opik: `mcp-egasedqaofxnzcqppuxi805h`, `run-enricher-kpop6yiy78vnlqaj9dxcaliy`.
- GitHub: REST API z fine-grained PAT; repo `zar-i-szlif` i `harness-zar-i-szlif`.

## 2. Tabela statusów

| ID | Objaw | Root cause | Status | Priorytet |
| --- | --- | --- | --- | --- |
| P7 | dokumentacja opisuje automatyczną promocję przez Actions | stary kontrakt po PR #156; PR #153 czeka | FIXED w harness, OPEN w produkcie | P1 |
| P8 | timer dead, service failed, `deployment_readback_failed_rollback_required` | 4-min okno readback + brak wznowienia pending | FIXED | P0 |
| P9 | Hindsight 402 | plugin czytał launch-scope `mode=cloud` | FIXED; retain/recall potwierdzony dla faktów operacyjnych | P0 |
| P10 | `succeeded` + `liveness=blocked` | brak bramki biznesowej na liveness | OPEN | P1 |
| P11 | 248 narzędzi, `mcp_paperclip__*` → Tool not found | podwójne połączenie Paperclip MCP + tłumaczenie nazw tool gateway | OPEN (fix opisany) | P0 |
| P12 | 402 „Insufficient credits” | SaaS Vectorize z launch config | FIXED razem z P9 | P0 |
| P13 | prod = HEAD otwartego PR #74 | Coolify śledzi gałąź funkcjonalną; CTO CHANGES_REQUESTED; fix `81fa3ae` | OPEN (re-review) | P0 |
| P14 | 13/14 agentów opencode_local | migracja zatrzymana na 1/14 | OPEN (zależne) | P1 |
| P15 | stage=agent, participant=user | **celowa eskalacja po 3 rundach** | MISDIAGNOSED | P2 |
| P16 | 748 recovery / 966 runów | backfill legacy + bieżące recovery | OPEN (metryka) | P2 |
| P17 | Opik MCP „tool failed internally” | CF Access 403 na wewnętrznym proxy | FIXED internal :8081; public OAuth → P18 | P1 |
| P18 | brak pozytywnego E2E OAuth Opik | brak service tokenu; guard wymaga `email` | OPEN (blokada polityki) | P1 |
| P19 | brak korelacji run→trace→span | run 36dbd bez trace; `model=unknown` 77/87 | OPEN | P1 |
| P20 | 4 PR Opik otwarte | tylko #53 wdrożony; #52←#39 | OPEN | P1 |
| P21 | enricher nie dowodzi retain/recall | 96 wzbogaconych; brak `thread_id`/span retain | OPEN | P2 |
| P22 | 15 banków, ui-qa=0 | brak porównania źródła | OPEN | P1 |
| P23 | izolacja 14 profili | Caddy OK; core ufa sieci Docker; 8888 niepubliczny | OPEN (hardening) | P2 |
| P24 | `latest-slim` bez digestu | brak pinowania obrazu | OPEN | P2 |
| P25 | `githubAuthenticationMode=host` | brak managed GitHub identity; push działa przez helper App | OPEN (tożsamość) | P1 |
| P26 | historyczny `Author identity unknown` | **brak awarii** — PR #158 dowodzi commita+push; autor = bot | FIXED funkcjonalnie / OPEN atrybucja | P2 |

## 3. P8 — kontroler promocji (FIXED)

### Objaw i dowód

- `product-native-promotion.timer`: `inactive (dead)` od 2026-11-06 19:30:32, mimo `enabled`.
- `product-native-promotion.service`: `failed`, `ExecMainStatus=1`, 19:29:59.
- Journal: `{"result":"denied","reason":"deployment_readback_failed_rollback_required"}`.
- Stan: `{"pending_sha":"0f6b646…","previous_sha":"b3dd661…","status":"readback_failed_rollback_required"}`.
- Wcześniejsze runy: `already_released` dla `b3dd661…`.
- Live o 21:21: `98cd058…`, `/healthz` 200 — produkt był zdrowy, padł tylko mechanizm.

### Root cause

1. Po patches `ci-approved` kontroler czekał `24 × 10 s = 240 s` na zmianę
   `/__release.json`. Build Coolify trwał dłużej (run 19:25:42–19:29:59).
2. Po timeoucie zapisał `pending_sha` i **nie cofnął** `ci-approved` (celowo), ale następny
   przebieg zaczynał od `if live != release: deny production_not_at_current_release_ref`
   i nie umiał wznowić oczekującego wdrożenia.
3. Timer został zatrzymany o 19:30:32 (ręczna decyzja operatorska), więc nie było retry.

### Wdrożona poprawka

Plik: `/usr/local/libexec/product_native_promotion.py` (backup:
`.bak-20261106-p8-readback`), źródło w harness:
`scripts/product_native_promotion.py`.

- `READBACK_ATTEMPTS=90`, `READBACK_INTERVAL=10` → 15 min.
- `wait_for_live(target)` wspólne dla ścieżki normalnej i wznowienia.
- Gałąź `pending`: jeśli `live != release`, `current == release`,
  `status=readback_failed_rollback_required` i `pending_sha == release`, kontroler czeka
  dalej zamiast fail-closed; po sukcesie zapisuje `healthy` i zwraca
  `deployed_after_retry`.
- Stary `pending` jest czyszczony, gdy live już równa się release.
- Drop-in systemd: `/etc/systemd/system/product-native-promotion.service.d/timeout.conf`
  z `TimeoutStartSec=1200`.

### Weryfikacja

- `python3 -m unittest test_product_native_promotion` → **19/19 OK** (3 nowe testy:
  wznowienie, fail-closed bez cofania ref, czyszczenie starego pending).
- `systemctl is-enabled` = `enabled`, `is-active` = `active`.
- Run 21:36:09: `{"live":"98cd058…","result":"already_released","sha":"98cd058…"}`.
- Stan po runie: `{"last_deployed_sha":"98cd058…","status":"healthy"}`.

### Pozostały test akceptacyjny

Następny realny, zatwierdzony merge na `main` musi przejść:
`main` → native review → `ci-approved` → Coolify → `/__release.json` = nowy SHA → `healthy`.
Dopiero to zamyka P8; obecny run to no-op.

Rollback: przywrócić backup skryptu i usunąć drop-in, `systemctl daemon-reload`.

## 4. P9/P12 — Hindsight Designera (FIXED configiem, E2E do potwierdzenia)

### Dowód

- `docker logs 2sganhx…` 2026-11-06 19:28: `Hindsight retain failed: (402)`,
  `recall failed: (402)`, `Insufficient credits. Please add credits to continue.`,
  `Via: 1.1 google`.
- Profil Designera:
  `/opt/data/profiles/designer/hindsight/config.json` ma `mode=local_external`,
  `api_url=http://hindsight-mcp-aglen8ervlo2lpi30oz8iii9:8080`, `bank_id=hermes-designer`,
  token banku Designera.
- Launch-scope `/opt/data/hindsight/config.json` ma `mode=cloud`, `bank_id=hermes`, pusty
  `apiKey`; proces gatewaya ma `HERMES_HOME=/opt/data`.
- `_load_config()` czytał najpierw `get_hermes_home()/hindsight/config.json`, więc **każdy**
  profil dostawał launch-scope cloud. Profile nigdy nie były czytane.
- Wszystkie 14 profili miało już poprawne configi `local_external` — to nie był brak
  konfiguracji, tylko błędna kolejność odczytu.

### Wdrożona poprawka

W 15 kopiach `plugins/hindsight/__init__.py` (14 profili + launch) `_load_config()` najpierw
czyta config leżący obok pluginu:

```python
local_home = Path(__file__).resolve().parents[2]
for path in (local_home / "hindsight" / "config.json",
             get_hermes_home() / "hindsight" / "config.json",
             Path.home() / ".hindsight" / "config.json"):
```

Backupy: `__init__.py.bak-20261106-profile-config`. Patch jest idempotentny i oznaczony
`shortcut: local hotfix 2026-11-06; replace with upstream profile-aware loader`.

### Weryfikacja

- Test resolvera: **14/14 OK**, każdy profil dostaje `mode=local_external`,
  `bank=hermes-<profil>`, URL MCP.
- Bezpośredni retain do `hermes-designer`: HTTP 200, `items_count=1` (fakt kontrolny
  „Ops connectivity probe 2026-11-06…”).
- Bezpośredni recall: HTTP 200, wynik z banku Designera.

### Pozostały test akceptacyjny

Następny realny run Designera (przez Paperclip) musi zalogować:
`Hindsight initialized: mode=local_external, api_url=http://hindsight-mcp-…, bank=hermes-designer`
oraz wykonać retain i recall bez 402.

Uwaga z próby E2E: gołe `POST /p/designer/v1/runs` (nawet z `session_id` i
`X-Hermes-Session-Key`) **nie inicjalizuje providera pamięci** — brak logu Hindsight i brak
402. To dowodzi tylko, że stateless API nie jest ścieżką, której używa Paperclip; nie
zamyka P9. Akceptacja wymaga runu z Paperclipa (adapter `hermes_gateway`).

### Retain/recall — wynik testu bezpośredniego (2026-11-06 22:40)

- Krótki syntetyczny canary (`designer-memory-canary-… = memory-canary-for-E2E-only`)
  został przyjęty (`HTTP 200`), ale ekstraktor zwrócił **0 faktów**:
  `Extract facts: 0 facts, 1 chunks`. Dokument ma 0 chunków i 0 jednostek.
- Ten sam canary w formie rozmowy i w formie akapitu z słowami „canary/synthetic/E2E”
  również dał 0 faktów — ekstraktor klasyfikuje takie treści jako nie-memorable.
- Długi, realistyczny fakt operacyjny (Designer = agent projektowy, model DeepSeek,
  provider opencode-go, panel na `98cd058`) dał **5 faktów** i 1 chunk.
- Recall na pytanie „Which model and provider does the Designer agent use?” zwrócił
  m.in. `Agent Designer używa modelu DeepSeek przez dostawcę opencode-go`,
  `Designer jest agentem projektowym firmy Zar i Szlif`,
  `Zespół zweryfikował, że self-hosted Hindsight przechowuje pamięć w banku hermes-designer`.

Wniosek: **retain i recall działają** dla realistycznych faktów. Nieudany test canary to
problem doboru treści (ekstraktor odfiltrował syntetyk), a nie brak zapisu. Recall zwraca
też obserwacje o nieudanym wyszukiwaniu, bo plugin zapisał narrację agenta jako
`observation`; przy `prefer_observations=true` mogą one dominować nad faktem źródłowym.

Do poprawy: nie traktować narracji „nie znalazłem” jako trwałej obserwacji (tag/filtr),
oraz testować pamięć realistycznym faktem operacyjnym, nie syntetycznym markerem.

### Ryzyko

- `hermes update` / reinstalacja pluginu może nadpisać lokalny patch. Trzeba to naprawić
  upstream (profile-aware loader) i dodać test regresyjny po aktualizacji.
- Produkcyjny obraz to PR #74 (P13); dopóki release nie jest z merge commita, łatka żyje
  tylko w wolumenie `/opt/data`.

## 5. P7 — dokumentacja promocji

### Fakty

- `product-ci.yml` ma tylko `validate-product`; `promote-release` i `verify-production`
  usunięto w PR #156.
- Produktowy `README.md` i `ops/coolify/CI_GATED_RELEASE.md` nadal opisywały stary
  automat. PR **#153** (`docs: remove obsolete product deployment claims from README`)
  to naprawia: README, `CI_GATED_RELEASE.md`, nowy `AGENTS.md`. Jest `mergeable=clean`,
  a Product CI na dokładnym HEAD `e3e7dad9…` jest **success**
  (run 42123235513).
- Harness `docs/RELEASE-POLICY.md` nadal opisywał `promote-release`; **poprawione w tym PR**.

### Ograniczenie, którego nie wolno pominąć

Kontroler P8 wymaga, aby **każdy** nowy merge na `main` miał natywną akceptację Paperclip.
Scalenie PR #153 bez takiej akceptacji zablokuje `ci-approved` na tym commicie
(`native_approval_unverified`) i zatrzyma przyszłe wydania produktu.

### Kolejność

1. Utworzyć/przypisać issue Paperclip dla PR #153 (work product `zar-i-szlif#153`).
2. Niezależny reviewer (CTO/CHO) zapisuje decyzję `approved` dla dokładnego HEAD.
3. Scalić PR #153 metodą merge commit (nie squash — kontroler wymaga 2 rodziców).
4. Poczekać na `validate-product` na merge commicie i na kontroler P8.
5. Zweryfikować `/__release.json` = merge SHA; jeśli dokumentacja nie zmienia artefaktu,
   kontroler i tak musi przejść readback.

Alternatywa tylko po jawnej decyzji CHO: pozostawić PR #153 otwarty do najbliższego
produktowego PR i scalić razem, aby ograniczyć liczbę blokowanych merge’y.

## 6. P10 — `succeeded` ≠ sukces biznesowy

### Dowód

Run `36dbd258-dcbd-4d61-b2a6-5e992fe337ce` (Designer, KOMAA-1627):
`adapter=hermes_gateway`, `status=succeeded`, `exit_code=0`, ale
`liveness_state=blocked`, `liveness_reason=Run output declared a concrete blocker`.
Issue zostało anulowane przez użytkownika, nie przez system.

### Naprawa

Bez zmian w Core Paperclipa (zakaz). Do wdrożenia w warstwie adaptera/boardu:

1. Traktować `liveness_state=blocked` jako **nieudany run biznesowy**: nie zamykać issue,
   nie uznawać work productu za gotowy, utworzyć recovery action z powodem.
2. Dodać do adaptera Hermes wymagany kontrakt wyjścia: `status`, `summary`,
   `evidence[]`, `blockers[]`; brak pola = `blocked`, nie `succeeded`.
3. Alert boardu, gdy run jest `succeeded` + `blocked` (dziś to cichy stan).

Test: wymuszony run z blokerem musi zakończyć się `blocked` i nie zmienić issue na `done`.

## 7. P11/P14 — narzędzia Paperclip w Hermesie i migracja agentów

### Dowód

- Run `b93de40e…`: Hermes uruchomił profil `designer` na DeepSeek, odczytał Wiki przez
  MCP z poprawnym hashem, ale katalog miał **248 narzędzi**.
- Nazwy: `mcp__editor_paperclip_assigned_268d2fcd__mcp_paperclip__<hash>`. Część
  `mcp_paperclip__*` kończy się:
  `MCPError: Tool "mcp.paperclip-mcp-4bbb3d2e:papercliplistruns" not found` oraz
  `MCPError: Server returned an error response`.
- W bazie są **dwie aktywne połączenia Paperclip MCP** o tym samym URL
  `http://paperclip-mcp:3101/mcp`:
  - `7551d8ac…` „Paperclip MCP”, `transport_config` poprawny, 200 wpisów katalogu;
  - `4bbb3d2e…` „Paperclip MCP · Hermes Designer dedicated” (utworzone 19:20),
    `transport_config = {}`, 200 wpisów katalogu.
- Oba profile są podpięte: general do **company**, dedicated do **company i agenta
  Designer** → agent widzi podwójny katalog (400 wpisów, po dedupie ~248).
- Eksperyment: usunięcie bindingów dedicated zostawiło tylko **41 narzędzi**
  (app-gallery/Plasmic + meta-tools), więc bindingi przywrócono. `transport_config`
  dedicated naprawiono na `config`.
- API Paperclipa raportuje 197 narzędzi, 167 wykonywalnych — projekcja do sesji Hermes jest
  niepełna.
- Gałąź `release/hermes-gateway-20261106-h02` zawiera scalony **PR #70** (native run-scoped
  MCP tools); prod #74 dokłada `install_run_mcp.py` (+10 linii).
- PR **#71** (`mergeable=false/dirty`) i **#73** są otwarte. Produkcja (P13) to HEAD PR #74,
  który nie zawiera #73.

### Naprawa

1. Zostawić **jedno** połączenie Paperclip MCP na agenta: usunąć dedicated profile
   (albo general z bindingów company) i ponownie wygenerować katalog; nie dopuszczać do
   dwóch profili wskazujących ten sam URL.
2. Naprawić tłumaczenie nazw w tool gateway: nazwa `mcp.<app>-<conn>:<tool>` musi być
   rozwiązywana do surowego `<tool>` przed wywołaniem upstream. To warstwa Core/MCP
   gateway — zgłosić wykonawcy, nie patchować Core.
3. Dodać preflight runu: jeśli `mcp_paperclip__*` nie rozwiązuje się do narzędzia
   upstream, run kończy się `blocked` przed wykonaniem pracy.
4. Dopiero potem migrować agentów (P14).

Test: realny run Designera ma jeden spójny katalog, a `paperclipListRuns` / issue
read/comment/status/checkout/resolve kończą się sukcesem, nie „Tool not found”.

Uwaga: heartbeat-invoke nie jest poprawnym canary — adapter odrzuca run bez issue/profilu
(„Hermes run-scoped MCP requires a named profile…”). Walidacja wymaga realnego issue-runu.

## 8. P13 — pochodzenie produkcyjnego Hermesa

### Dowód

- Prod `2sganhxhhnioiqh4an9g2f4k` (`hermes-gateway`): obraz
  `a793aa2434845bf7f02d72eadba532e56beb721e` = **HEAD otwartego PR #74**.
- Coolify app prod ma `git_branch = fix/hermes-runmcp-tool-projection-20261106`
  (gałąź funkcjonalna, nie release), `git_commit_sha` puste, brak obrazu z rejestru —
  build lokalny tagowany SHA.
- Oczekiwana gałąź `release/hermes-gateway-20261106-h02` ma tip `b64d1d31…`;
  `compare/release...a793aa2` = **diverged, ahead 2 / behind 1**, różnica tylko
  `integrations/hermes-paperclip/gateway/install_run_mcp.py` (+10).
- Deploye prod: `a793aa2` 18:12, `6be5104` 18:01, `663e63b` 17:47 — wszystkie
  `is_webhook=false` (manual/API), nie webhook z gałęzi.
- Candidate `hut52do8…` = `40bae449…` (PR #71, `mergeable=false/dirty`, konflikt z `main`).
- Canary `e6558590…` = tip `fix/hermes-runmcp-authority-20261106`, **bez PR**.
- PR #74: 1 plik, +10/−0, `mergeable=true/clean`, **brak CI i review**; opis twierdzi E2E
  na tym SAMYM SHA — czyli kod z niezatwierdzonego PR jest już na produkcji.
- CTO dał **CHANGES_REQUESTED**: `_project_scoped_tools` chwilowo modyfikuje współdzielony
  stan narzędzi agenta, a testy nie dowodzą izolacji przy równoległych runach, anulowaniu
  i wyjątkach. To realna luka, nie formalność.
- **Poprawka wypchnięta do PR #74** (commit `81fa3ae`): per-agent `RLock` trzymany przez
  cały czas projekcji, test współbieżny, test wyjątku i przywrócenia inwentarza.
  Wymaga re-review CTO przed merge.
- Obrazy nie mają etykiet repo/commit; jedynym provenance jest tag SHA + compose labels.

### Naprawa

1. Review PR #74 (1 plik, +10) i **scalić do `release/hermes-gateway-20261106-h02`**.
2. Ustawić Coolify prod `git_branch = release/hermes-gateway-20261106-h02` (albo pinowany
   digest obrazu zbudowanego z merge SHA).
3. Zbudować i wdrożyć z merge SHA; odczytać tag/digest i potwierdzić zgodność.
4. Canary zostaje jedynym miejscem deployu z gałęzi funkcjonalnych/PR.
5. Guard w ops: jeśli `coolify.pullRequestId != 0` albo gałąź prod nie jest `release/*`,
   deploy jest odrzucany.

Test: `docker inspect` prod pokazuje merge SHA gałęzi release; PR #74 zamknięty jako
scalony; canary nadal na `e655859…` (lub nowszym) i nie jest prod.


## 9. P14 — migracja 14 agentów

Stan: 13 × `opencode_local`, 1 × `hermes_gateway` (Designer). To 1/14, nie cutover.

Kolejność (twarde bramki):

1. P13: prod z merge commita.
2. P11: wymagane narzędzia Paperclip dostępne.
3. P9/P12: Hindsight `local_external` + retain/recall 200.
4. P22/P23: banki i izolacja potwierdzone dla danego agenta.
5. P18/P19: Opik przyjmuje trace i koreluje run.
6. Jeden agent → canary run → E2E issue read/comment/status/commit → rollback do
   `opencode_local` przy błędzie.
7. Dopiero następny agent. Bez migracji „falą”.

Test: tabela 14/14 z adapterem, bankiem, ostatnim runem i dowodem E2E; brak wpisu = brak
cutoveru.

## 10. P15 — review participant (MISDIAGNOSED)

Dowód:

- KOMAA-1594 i KOMAA-1615: `execution_state.changesRequestedCount=3`,
  `lastDecisionOutcome=changes_requested`.
- Kod `issue-execution-policy.ts`: po osiągnięciu `maxReviewRounds` (domyślnie 3) reviewer
  agent jest zastępowany przez `responsibleUserId`; stan jest „sticky” do decyzji człowieka.
- `currentParticipant.type=user` jest więc **poprawny** dla eskalacji, a nie dowodem
  rozjazdu z etapem.

Działanie:

- Nie wymuszać SQL-em agenta z powrotem — to złamie kontrakt eskalacji.
- Decyzja człowieka na KOMAA-1594/1615 (approve/reject) albo jawna zmiana
  `maxReviewRounds` w polityce.
- Dodać alert boardu „review escalated to human”, żeby nie wyglądało to jak zawieszony run.
- W audycie P15 poprawić opis: to nie błąd runtime.

## 11. P16 — recovery

Dane z `issue_recovery_actions` (od 2026-11-02, niepełny tydzień):

- 748 akcji / 929 runów = 0,81 akcji/run (80,5% na poziomie zdarzeń, nie unikalnych runów).
- 2026-11-03: 520 akcji / 143 runy — jednorazowy backfill
  `legacy_execution_requires_reconciliation` (562 akcji w tygodniu).
- Po 11-03: 41–93 akcje/dzień przy 138–269 runach.
- Inne przyczyny: `deliberate_wait_without_target` (87+32), `workspace_validation_failed`,
  `execution_review_participant_recovery`, `successful_run_missing_state`.

Naprawa metryki i procesu:

1. Rozdzielić backfill legacy od bieżących akcji (tag `source=legacy_backfill`).
2. Liczyć unikalne runy z co najmniej jedną akcją, nie sumę akcji.
3. SLO: <2% unikalnych runów/tydzień po zakończeniu backfillu; alert tylko na bieżące.
4. Osobno śledzić `workspace_validation_failed` (konfiguracja projektu: `local_path` +
   `isolated_workspace` daje `workspace_validation_failed` przed startem adaptera).
5. Nie traktować `deliberate_wait_without_target` jako awarii, jeśli issue ma jawny cel
   oczekiwania; inaczej dodać wymóg targetu.

## 12. P17–P21 — Opik

### P17 — MCP „tool failed internally” (root cause potwierdzony)

Topologia: realny upstream to `opik-mcp-egasedqaofxnzcqppuxi805h` (192.168.176.3),
przed nim `proxy-egased…` (nginx :8080) i `access-guard-egased…` (:8088). Kontener
`mcp-egased…` jest nieużywanym duplikatem.

Przyczyna:

- `opik-mcp` przyjmuje dowolny niepusty bearer i nie wymaga klucza (Opik OSS).
  `initialize` + `tools/call list project` zwraca **16 projektów**; API Opik
  `…/api/v1/private/projects` → 200.
- Nginx `location /` **zawsze** wykonuje `auth_request /__access_verify`; guard wymaga
  ważnego Cloudflare Access JWT z claimem `email`. Brak JWT → **403** i MCP nigdy nie
  jest wołany (jego log w tym czasie jest pusty).
- Config Paperclipa `/paperclip/.config/opencode/opencode.jsonc` ma:
  `"opik": { "url": "http://proxy-egased…:8080/mcp", "oauth": false }`.
  Klient nie wysyła JWT i nie uruchamia OAuth → każde wywołanie to 403.
- W logu nginx: **42 × 403** z UA `opencode/1.19.3`, źródło `172.19.0.17` = kontener
  Paperclipa. To dokładnie „The tool failed internally”.
- Niezależnie: połączenie `tool_connections` „Opik MCP — E2E read-only” ma
  `health_status=failed`, „OAuth credentials have expired”, `last_success 2026-11-01
  19:39Z`, scopes `[]` (brak `offline_access` → brak refresh).

Naprawa (wdrożona 2026-11-06):

1. Dodano w nginx **wewnętrzny listener `:8081`** bez `auth_request`, dostępny tylko
   z sieci Docker (`allow 172.19.0.0/16`, `192.168.176.0/20`, `127.0.0.1`, `deny all`).
   Publiczny `:8080` z Cloudflare Access pozostał bez zmian.
   Plik: `/home/opencode/projects/opik/mcp-proxy.conf` (backup
   `.bak-20261106-internal`), `nginx -t` + reload OK.
2. Config Paperclipa `/paperclip/.config/opencode/opencode.jsonc` wskazuje teraz
   `http://proxy-egasedqaofxnzcqppuxi805h:8081/mcp` (backup
   `.bak-20261106-opik-internal`).
3. Test z kontenera Paperclipa: `initialize` → HTTP 200 (`opik-mcp 1.30.0`);
   `tools/call list entity_type=project` → **16 projektów**. Ścieżka wewnętrzna działa.
4. Publiczne połączenie `tool_connections` „Opik MCP — E2E read-only” nadal ma wygasły
   OAuth — to P18, osobna sprawa.

### P18 — pozytywny E2E OAuth (blokada polityki, nie awaria)

- Publiczny well-known zwraca poprawne metadane CF Access Managed OAuth
  (`authorization/token/registration`, PKCE S256).
- **Nie istnieje żaden użyteczny service token** dla Opik; guard wymaga claimu `email`,
  więc token service (common_name) zostałby odrzucony. Jedyne działające poświadczenie to
  interaktywne logowanie człowieka w Cloudflare Access.
- Zatem pozytywny E2E (`tools/list`, `tools/call`, odczyt projektu i trace) **musi**
  wykonać człowiek w przeglądarce albo trzeba rozszerzyć guard o service tokeny.
- PR #51 scalony 2026-11-05 19:55; opis KOMAA-1605 nadal wymienia go jako otwarty —
  zaktualizować.

### P19/P20/P21 — korelacja i koszt

- Run `36dbd258…`: 316 276 / 8 415 tokenów, `model=unknown`, `costUsd=null`,
  `costStatus=unpriced`, `usageByModel=null`; **brak trace w Opik** (projekt
  `paperclip-a9de363c` ma 5 trace’ów, ostatni 12:24Z; run start 19:24Z).
- `cost_events` 30 dni: `hermes_gateway` 87 zdarzeń, **87 unpriced, 0 kosztu**, model
  `unknown` w 77/87; `openai` 2201 zdarzeń `gpt-6-luna` raportowane jako **0.0**;
  tylko `opencode-go` ma realne koszty (deepseek 6,89 ¢, muse 3,21 ¢).
- Spany LLM w Opik mają usage (prompt/completion/cache/reasoning), `paperclip_run_id`,
  `agent_id`, `provider`, `provider_reported_cost_usd`, ale **brak `model`**
  i `total_estimated_cost=null`.
- Enricher (obraz = PR #53, `7110929…`): 1154 cykle, **96 wzbogaconych**, 12 błędów
  (4 unikalne runy, `HTTPError`), ~35 698 skipped. Korelacja po
  `metadata.paperclip_run_id` + `metadata.agent_id`; **brak `thread_id`** i brak
  `hermes_run_id`.
- PR: #39 open (30 ahead/166 behind), #45 open (15/166), #49 open (9/131), #52 open
  (base = #39, 39/166), #53 merged i wdrożony. Tylko #53 jest na produkcji.

Kolejność: #39 → #52, #45, #49; deploy enrichera z merge SHA; uzupełnić:
`paperclip_run_id`, `hermes_run_id`, `opik_thread_id` (= `paperclip_run_id`),
`model`, `cost`; dodać cennik dla `openai`/`hermes_gateway` albo oznaczyć
`unpriced` jawnie w UI.

Test akceptacyjny: jeden pełny run ma wszystkie 4 identyfikatory, `model`, koszt
(liczony lub jawnie `unpriced`) oraz co najmniej jeden span retain i recall Hindsight.


## 13. P22–P24 — Hindsight / Vectorize

### P22 — kompletność banków (dane potwierdzone)

Snapshot 2026-11-06 21:39 UTC. Wszystkie **15 banków** istnieje: 14 `hermes-*` +
`chatgpt-assistant`. Łącznie **124 fakty** (world 31 / experience 38 / observation 55),
**111 dokumentów**, 88 chunków, 113 encji, 485 linków.

| bank | fakty | dokumenty | chunki | uwagi |
| --- | ---: | ---: | ---: | --- |
| hermes-cho | 50 | 25 | 24 | największy |
| hermes-cpo | 29 | 29 | 14 | 15 dokumentów bez chunków |
| hermes-engineer | 13 | 8 | 9 | źródło −4 fakty (invalidacje) |
| hermes-harness-engineer | 8 | 3 | 3 | |
| hermes-ceo | 5 | 7 | 7 | |
| chatgpt-assistant | 3 | 2 | 2 | utworzony lokalnie 11-04, nie z migracji |
| hermes-mascot-designer | 3 | 4 | 4 | źródło −5 faktów |
| hermes-coo/cto/designer/email-creative/lifecycle-ops/mcp-engineer | po 2 | 2–6 | 2–5 | |
| hermes-cmo | 1 | 5 | 5 | |
| **hermes-ui-qa** | **0** | **6** | **4** | 4 stare dokumenty bez faktów, 2 nowe bez chunków |

Porównanie z manifestem źródłowym (archiwum SaaS z 2026-11-03): źródło 126 nodes / 78 docs,
lokalnie 121 nodes / 109 docs w 14 bankach. Różnice: cpo +8 nodes/+21 docs,
cho +2 docs, designer +4 docs, email +2, ui-qa +2; engineer −4, mascot −5,
mcp-engineer −4 (nowe invalidacje).

`hermes-ui-qa=0` **nie jest utratą faktów**: źródło też miało 0 faktów i 4 invalidated.
Lokalnie brakuje jednak historii invalidacji (0 vs 4), a dwa najnowsze dokumenty nie mają
chunków. To wymaga wyjaśnienia, ale nie blokuje banku.

Wnioski do planu:

1. Porównanie countów **przeszło** dla faktów; nie przeszło dla historii invalidacji
   (źródło 29, lokalnie 19, inna dystrybucja) i części dokumentów bez chunków/faktów.
2. `bank_stats_cache` jest niespójny z DB (ui-qa 4 vs 6 docs; cho entity 49 vs 0 linków
   typu entity). Nie używać cache jako dowodu migracji.
3. `banks.last_consolidated_at` jest NULL dla wszystkich banków — tylko cache ma wartości.
4. `audit_log` = 0 mimo zapisów; brak lokalnego audytu.
5. Raport migracji musi zawierać: źródłowy manifest + SHA, count per tabela, listę
   invalidacji, listę dokumentów bez chunków/faktów i datę snapshotu.

### P23 — izolacja (potwierdzona w Caddy, słaba w core)

Testy na gatewayu (Caddy, port 8080):

| żądanie | status |
| --- | --- |
| token CHO → bank `hermes-cho` recall | 200 |
| token Designer → bank `hermes-cho` | 404 |
| token CHO → bank `hermes-designer` | 404 |
| brak tokenu → bank `hermes-cho` | 404 |
| token CHO → MCP `/mcp/hermes-cho/` | 200 |
| token Designer → MCP `/mcp/hermes-cho/` | 404 |
| token Designera → MCP `/mcp/hermes-designer/` | 200 |
| admin token → `/mcp?access_token=…` | 200 (39 narzędzi, w tym `delete_bank`) |

Pozytywnie: MCP recall po ścieżce CHO zwrócił 5 ID, wszystkie 5 w `hermes-cho`.
Per-bank MCP nie przyjmuje `bank_id` — nie da się nim wybrać obcego banku.

**Luka wewnętrzna (nie publiczna):** `GET http://hindsight:8888/v1/default/banks` bez
auth zwraca wszystkie 15 banków, a recall dowolnego banku działa bez tokenu. Potwierdzona
konfiguracja sieci: port **8888 nie jest publikowany na hoście** (`127.0.0.1:8888` nie
łączy), a kontener Hermes spoza prywatnych sieci Hindsight **nie uzyskał** połączenia
z backendem. Nie ma dowodu publicznego dostępu do pamięci i nie ma podstaw do wyłączania
Hindsight. Izolacja banków działa w Caddy; backend ufa każdemu klientowi w swojej sieci
Docker. To luka wewnętrzna, nie wystawienie na Internet.

Do wdrożenia (wzmocnienie, nie incydent):

1. Włączyć auth w Hindsight core (token API / mTLS) albo ograniczyć sieć do niezbędnych
   kontenerów i usunąć z niej enricher.
2. Admin MCP: token w query stringu jest logowany przez proxy; przenieść do nagłówka,
   ograniczyć narzędzia mutujące, rotować token.
3. Dodać test: kontener bez uprawnień nie może odczytać banku przez 8888.
4. Test izolacji po restarcie i zmianie sesji: dane w named volume
   `hjda7ckq5z4luhd1vpdepi0r_hindsight-postgres` przeżyły recreate 2026-11-06 (dowód:
   dokumenty z 11-04/11-05). Brak jednak backupu — volume to jedyna kopia.

### P24 — pinowanie obrazu

- Hindsight: `ghcr.io/vectorize-io/hindsight@sha256:c7d494c3…` (tag `latest-slim`,
  mutowalny). Postgres: `pgvector/pgvector@sha256:7d0a4146…`. Caddy: `d8542f48…`.
- Runtime **nie zależy od SaaS**: `HINDSIGHT_CP_DATAPLANE_API_URL=http://localhost:8888`,
  `HINDSIGHT_ENABLE_CP=false`. Stare poświadczenie SaaS istnieje tylko w archiwalnym
  wolumenie `.env` i skrypcie eksportu; nie jest używane przez działający proces.
- Do wdrożenia: pin digestów w manifeście, test odtworzenia z digestu, backup/restore
  named volume, rollback do poprzedniego digestu.
- Publiczny gateway `https://hindsight-mcp.kompaszbiorek.pl` zwracał 404 z Cloudflare
  w tym odczycie; routing publiczny jest niepotwierdzony (Hermes używa adresu wewnętrznego,
  więc nie blokuje to P9).


## 14. P25/P26 — GitHub auth i tożsamość commita

### P25 — auth w runach (częściowo misdiagnosed)

Dowód:

- `heartbeat_runs.context_snapshot.githubAuthenticationMode`: **host = 4009**,
  managed = 0, null = 5135; ostatnie 3 dni: host 602, managed 0.
  Dozwolone wartości to tylko `host|managed` — nie ma trybu `github-app`.
- `run_identity_contexts.github` (1990/4932) =
  `{"reason":"No GitHub identity connected","source":"personal","status":"absent"}`.
- **Push jednak działa**: Engineer run `efd2f8b0-1bc1-4f82-9b31-8ee3acdc3ac9`
  (KOMAA-1628) wykonał `git commit` + `git push origin KOMAA-1628`, SHA
  `c0ac4f1f9e3bc0e900acfba39702767170735063` → PR **#158** → merge
  `98cd058155…` (obecny live).
- Mechanizm: w kontenerze Core jest globalny helper
  `credential.https://github.com.helper=!/paperclip/github-auth-bin/core-git-credential-app`,
  który używa instalacyjnego tokenu GitHub App. Timer
  `paperclip-github-app-refresh.timer` (enabled/active, co 20 min) odświeża token dla
  App `5398752` / installation `173456397`, repo `harness-zar-i-szlif` + `zar-i-szlif`,
  perms `contents:write, pull_requests:write, metadata:read, checks:read`.
- Autor commita to `miloszspyrka-code <233741877+miloszspyrka-code@users.noreply.github.com>`
  (bot), nie tożsamość agenta/runu.
- CTO ma per-agent `GIT_CONFIG_VALUE_0="!gh auth git-credential"`, a w kontenerze nie ma
  zalogowanego `gh` — to realny błąd tylko dla tego agenta.

Naprawa:

1. Skonfigurować managed GitHub identity (`githubSelection.configured`), aby runy
   raportowały `managed` i miały wpis w `run_identity_contexts`, zamiast polegać na
   globalnym helperze i trybie `host`.
2. Usunąć per-agent override `!gh auth git-credential` z CTO; użyć helpera App.
3. Zdecydować politykę autora commita: bot App (dziś) czy tożsamość agenta. Jeśli agent,
   ustawiać `user.name`/`user.email` per run i weryfikować w GitHub.
4. Test negatywny: brak grantu/installation → run `blocked`, nie cichy fallback do hosta.

### P26 — commit author (FIXED funkcjonalnie)

Historyczny `GIT_FAILED: Author identity unknown` **nie występuje** w dzisiejszych runach:
wszystkie znalezione wystąpienia to tekst promptów zadaniowych, nie błąd runtime.
Dowodem domknięcia jest PR #158 (commit `c0ac4f1f`, push, merge, deploy).

Pozostaje polityka atrybucji: commit ma autora bota, nie agenta. Test akceptacyjny:
commit z runu ma `author` równy uzgodnionej tożsamości (bot lub agent) i ten sam SHA
w remote, PR i `/__release.json`.

## 15. Kolejność wdrożeń (jedna ścieżka)

1. **P8** — zrobione; czeka na następny realny merge.
2. **P9/P12** — zrobione; potwierdzić logiem następnego runu Designera.
3. **P13** — re-review PR #74 po `81fa3ae` (izolacja współbieżna), merge do release,
   przełączyć Coolify prod na `release/*`, rebuild z merge SHA, guard na PR-head.
4. **P11** — jeden profil Paperclip MCP na agenta, naprawa tłumaczenia nazw w tool
   gateway, preflight narzędzi, E2E na nowym prod.
5. **P15** — decyzja człowieka na KOMAA-1594/1615 (nie SQL).
6. **P7** — review + merge PR #153 po natywnej akceptacji.
7. **P25** — managed GitHub identity, usunięcie override CTO, polityka autora; P26
   funkcjonalnie domknięte PR #158, została tylko atrybucja.
8. **P17/P18** — Opik MCP fix + pozytywny OAuth E2E.
9. **P19/P20/P21** — PR #39→#52, #45, #49; deploy enrichera; korelacja.
10. **P22/P23/P24** — kompletność, izolacja core, digest, backup.
11. **P14** — migracja agentów pojedynczo po wszystkich bramkach.

## 16. Testy akceptacyjne (minimalny zestaw E2E)

| Obszar | Test | Kryterium |
| --- | --- | --- |
| P8 | unit + realny merge | 19/19; nowy SHA w `/__release.json` |
| P9 | realny run Designera | `mode=local_external`, retain/recall 200 |
| P10 | run z blokerem | issue nie `done`, alert |
| P11 | `tools/list` w runie | 5 wymaganych operacji issue |
| P13 | `docker inspect` prod | merge SHA release, nie PR head |
| P15 | decyzja człowieka | issue wychodzi z `in_review` |
| P17/P18 | MCP + OAuth | `list_projects`, `read_trace` |
| P19 | jeden run | 4 identyfikatory + spany retain/recall |
| P23 | token A na banku B | 401/404 |
| P25/P26 | commit+push+PR | author = tożsamość runa, SHA zgodny |

## 17. Rollback

- P8: backup skryptu + usunięcie drop-inu; `daemon-reload`; timer zostaje zatrzymany,
  jeśli nowy run miałby promować niezatwierdzony SHA.
- P9: przywrócić `__init__.py.bak-20261106-profile-config` w profilach; launch config
  pozostaje nietknięty.
- P13: Coolify rollback do ostatniego zdrowego obrazu (digest), nie force-push ref.
- P25: przywrócić poprzedni adapter config; runy bez grantu mają fail-closed, nie host.

## 18. Czego nie zweryfikowano

- P9: retain/recall potwierdzony bezpośrednio dla realistycznych faktów operacyjnych;
  syntetyczny canary został odfiltrowany przez ekstraktor (0 faktów). Brak jeszcze
  potwierdzenia w realnym runie Paperclipa po restarcie gatewaya.
- P8: brak nowego merge produktu po naprawie (tylko no-op `already_released`).
- P13: poprawka `81fa3ae` jest w PR #74, ale nie ma re-review CTO, merge ani deployu.
  Produkcja nadal na `a793aa2`.
- P11: potwierdzone dwa połączenia i podwójny katalog; bindingi przywrócone, transport
  dedicated naprawiony. Nie udało się wykonać ważnego canary — heartbeat-invoke odrzuca
  run bez issue/profilu. Test wymaga realnego issue-runu. Tłumaczenie nazw tool gateway
  nie zostało naprawione (warstwa Core/MCP gateway).
- P17: wewnętrzny listener `:8081` i config Paperclipa wdrożone; `list project` zwraca
  16 projektów. Publiczna ścieżka OAuth nietknięta (P18).
- P18: pozytywny OAuth wymaga interaktywnego logowania człowieka; nie wykonano.
- P19/P20/P21: nie mergowano PR Opik ani nie deployowano enrichera.
- P22/P23/P24: nie zmieniano Hindsight; luka wewnętrznego `:8888` pozostaje otwarta,
  publicznego dostępu nie potwierdzono.
- P25/P26: nie zmieniano managed identity ani autora commita; push działa (PR #158).
- Nie zmieniano Paperclip Core. Wszystkie odczyty DB były `SELECT` poza kontrolowanymi
  zapisami danych: przywrócenie bindingów, `transport_config` dedicated, wpisy kontrolera,
  drop-in systemd i pliki pluginów Hindsight.

