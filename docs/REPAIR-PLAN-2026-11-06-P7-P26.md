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
  w 15 kopiach pluginu; 14/14 profili ładuje własny bank i endpoint MCP. Self-hosted
  retain/recall zwraca HTTP 200.
- **P7 (część harness)** — `docs/RELEASE-POLICY.md` nadal opisywał usunięty `promote-release`;
  poprawiono w tym PR. Produktowy PR #153 nadal wymaga review (patrz P7).

Najważniejsze otwarte blokery:

- **P11/P14** — Hermes nie ma natywnych narzędzi Paperclip w realnym runie; 13/14 agentów
  nadal na `opencode_local`. To blokuje migrację.
- **P13** — produkcyjny Hermes działa z HEAD otwartego PR #74, nie z merge commita gałęzi
  release.
- **P17/P18** — odczyt projektów Opik przez MCP zawodzi; brak pozytywnego E2E OAuth.
- **P25/P26** — realne runy CTO/CHO używają `githubAuthenticationMode=host`, a w kontenerze
  Paperclipa nie ma poświadczenia `gh`; brak dowodu commita z tożsamością runa.
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
| P9 | Hindsight 402 | plugin czyta launch-scope `mode=cloud` | FIXED (config), E2E do potwierdzenia | P0 |
| P10 | `succeeded` + `liveness=blocked` | brak bramki biznesowej na liveness | OPEN | P1 |
| P11 | 51 narzędzi, brak control-plane Paperclip | projekcja narzędzi per-run; PR #71/#73 otwarte | OPEN | P0 |
| P12 | 402 „Insufficient credits” | SaaS Vectorize z launch config | FIXED razem z P9 | P0 |
| P13 | prod = HEAD otwartego PR #74 | Coolify śledzi gałąź/PR zamiast merge release | OPEN | P0 |
| P14 | 13/14 agentów opencode_local | migracja zatrzymana na 1/14 | OPEN (zależne) | P1 |
| P15 | stage=agent, participant=user | **celowa eskalacja po 3 rundach** | MISDIAGNOSED | P2 |
| P16 | 748 recovery / 966 runów | backfill legacy + bieżące recovery | OPEN (metryka) | P2 |
| P17 | Opik MCP „tool failed internally” | do potwierdzenia (raport w toku) | OPEN | P1 |
| P18 | brak pozytywnego E2E OAuth Opik | test negatywny ≠ test pozytywny | OPEN | P1 |
| P19 | brak korelacji run→trace→span | model/cost null, thread_id nie mapowany | OPEN | P1 |
| P20 | 4 PR Opik otwarte | zależność #52←#39 | OPEN | P1 |
| P21 | enricher nie dowodzi retain/recall | snapshot statystyk ≠ span | OPEN | P2 |
| P22 | 15 banków, ui-qa=0 | brak porównania źródła | OPEN | P1 |
| P23 | brak testów izolacji 14 profili | tylko pojedyncze dowody | OPEN | P0 |
| P24 | `latest-slim` bez digestu | brak pinowania obrazu | OPEN | P2 |
| P25 | `githubAuthenticationMode=host` | brak managed GitHub App w runie | OPEN | P0 |
| P26 | brak E2E commita z tożsamością | historyczny `Author identity unknown` | OPEN | P1 |

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

- Run Designer widział 51 narzędzi: 47 Plasmic/Wiki, 1 `todo`, 3 `wiki_fs`
  (`MCP server 'wiki_fs' is not connected`), brak issue read/comment/status/checkout/resolve.
- API Paperclipa raportuje 197 narzędzi, 167 wykonywalnych — projekcja do sesji Hermes jest
  niepełna.
- PR **#71** (`expose run-scoped Paperclip Named MCP tools`) i **#73**
  (`expose Paperclip runtime tools as native per-run Hermes`) są otwarte.
- Produkcja (P13) to HEAD PR #74, który nie zawiera #73.

### Naprawa

1. Scalić #71/#73 do gałęzi release (po review) — bez tego migracja 13 agentów jest
   bezcelowa.
2. Zbudować nowy obraz z merge commita (P13) i wdrożyć jako prod.
3. Dodać preflight runu: jeśli brakuje którejkolwiek z wymaganych operacji
   (`issue.read`, `issue.comment`, `issue.status`, `issue.checkout`, `issue.resolve`),
   run kończy się `blocked` przed wykonaniem pracy.
4. Dopiero potem migrować agentów pojedynczo (P14), z canary i rollbackiem.

Test: realny run Designera ma w `tools/list` wszystkie wymagane operacje i wykonuje
odczyt + komentarz + zmianę statusu issue.

## 8. P13 — pochodzenie produkcyjnego Hermesa

### Dowód

- Prod `2sganhxhhnioiqh4an9g2f4k`: tag `a793aa243484…` = HEAD PR **#74** (otwarty).
- Candidate `hut52do8…`: `40bae449980e…` = HEAD PR **#71**.
- Canary `yh20mb2…`: `e6558590e063…`.
- Gałąź docelowa PR #74: `release/hermes-gateway-20261106-h02` (do potwierdzenia w raporcie
  Coolify, sekcja 12).

### Naprawa

1. PR #74 musi zostać zrecenzowany i **scalony** do gałęzi release; prod ma być budowany
   z merge SHA, nie z HEAD PR.
2. Coolify: produkcja śledzi tylko `release/*` (albo pinowany digest), PR-head deploy
   dozwolony wyłącznie dla canary.
3. Po wdrożeniu odczytać etykietę/digest obrazu i potwierdzić, że odpowiada merge SHA.
4. Dodać guard w CI/ops: jeśli obraz prod ma etykietę `pullRequestId != 0`, deploy jest
   odrzucany.

Test: `docker inspect` prod pokazuje merge SHA gałęzi release; PR #74 pozostaje historią.

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

### P17 — MCP „tool failed internally”

Do potwierdzenia w raporcie infrastrukturalnym (kontenery zdrowe: backend 2.2.121,
MCP 3.0.7, access-guard, enricher). Plan:

1. Odtworzyć `tools/list` i `tools/call` wewnątrz sieci, z tym samym tokenem co klient.
2. Zebrać log MCP w momencie błędu (status upstreamu, nagłówki, projekt).
3. Rozdzielić: błąd narzędzia (handler) vs błąd upstreamu (401/403/500) vs zły URL API.
4. Naprawić handler/konfigurację; dodać test `list_projects` + `read_trace` do smoke.

### P18 — pozytywny E2E OAuth

Wymagane: realny użytkownik po Cloudflare Access Managed OAuth wykonuje
`tools/list`, `tools/call`, odczyt projektu i konkretnego trace. Same testy negatywne
(brak JWT, zły aud) nie zamykają P18. PR #51 jest już scalony — opis KOMAA-1605 wymaga
aktualizacji.

### P19/P20/P21 — korelacja i koszt

- Run `36dbd258…`: 316 276 tokenów wejściowych, 8 415 wyjściowych, `model=unknown`,
  `costUsd=null`, `costStatus=unpriced`, `usageByModel=null`.
- PR #39 (segmentacja ról/Hindsight), #45 (LLM usage/cache/spany), #49 (kanoniczny
  eksporter/NDJSON), #52 (metadane Hindsight/LLM + migracja; baza #39) — otwarte;
  #53 scalony.
- Enricher: `runs_enriched=0/1`, `runs_skipped≈73–85`, `runs_failed=0` — skipped nie jest
  błędem, ale nie dowodzi retain/recall.

Kolejność: #39 → #52, #45, #49; deploy enrichera z merge SHA; dodać do runu:
`paperclip_run_id`, `hermes_run_id`, `opik_thread_id`, `trace_id`, `model`, `cost`.
Test akceptacyjny: jeden pełny run ma wszystkie identyfikatory i co najmniej jeden span
retain oraz recall Hindsight.

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

**Luka bezpieczeństwa (P0/P1):** bezpośrednie `http://hindsight:8888` **nie wymaga
uwierzytelnienia**. `GET /v1/default/banks` bez auth zwraca wszystkie 15 banków, a recall
dowolnego banku działa bez tokenu. Izolacja istnieje **tylko w Caddy**. Każdy kontener
w sieci `hindsight-isolated` (gateway, admin, enricher) może czytać wszystkie banki.
Port 8888 nie jest opublikowany na hoście, ale to nie jest granica bezpieczeństwa.

Do wdrożenia:

1. Włączyć auth w Hindsight core (token API / mTLS) albo ograniczyć sieć do niezbędnych
   kontenerów i usunąć enricher z tej sieci.
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


## 14. P25/P26 — GitHub App i tożsamość commita

### P25 — auth w runach

Dowód:

- `context_snapshot.githubAuthenticationMode = "host"` na **wszystkich 4009 runach od
  2026-10-01** (CTO, CHO i inne) — to jedyna wartość w danych.
- W kontenerze Paperclipa: `gh auth status` → **not logged in**; brak `/paperclip/.config/gh`,
  brak `GITHUB_*`/`GH_*`; `HOME=/paperclip`, uid 0.
- Na hoście root też nie jest zalogowany; `ubuntu` jest zalogowany do `github.com`
  (konto `miloszspyrka-code`, scopes `gist, read:org, repo, workflow`), ale runy nie
  działają jako `ubuntu`.
- Dwa historyczne połączenia GitHub zostały zarchiwizowane; brak aktywnych grantów dla
  agentów; izolowany Git kończył się kodem 128.

To wyjaśnia, dlaczego centralny MCP widzi repo, a run nie może wykonać git.
Plan:

1. Wymusić managed GitHub App installation auth dla workspace/runs; usunąć fallback do
   `host`.
2. Zweryfikować, że run dostaje instalacyjny token o zakresie tylko do potrzebnego repo.
3. Dodać do runu pole `githubAuthenticationMode` z wartością `github-app-installation`
   i test negatywny: brak grantu = run `blocked`, nie cichy fallback.
4. E2E: run tworzy commit, push, PR; odczytać SHA z GitHub.

### P26 — commit author

Wymagane: realny commit z `user.name`/`user.email` tożsamości agenta, `remoteSha`,
push, PR i odczyt tego samego SHA. Historia `GIT_FAILED: Author identity unknown`
nie może być uznana za zamkniętą bez tego testu.

## 15. Kolejność wdrożeń (jedna ścieżka)

1. **P8** — zrobione; czeka na następny realny merge.
2. **P9/P12** — zrobione; potwierdzić logiem następnego runu Designera.
3. **P13** — merge PR #74 do release, rebuild prod z merge SHA, guard na PR-head.
4. **P11** — merge #71/#73, preflight narzędzi, E2E.
5. **P15** — decyzja człowieka na KOMAA-1594/1615 (nie SQL).
6. **P7** — review + merge PR #153 po natywnej akceptacji.
7. **P25/P26** — managed GitHub App + E2E commit.
8. **P17/P18** — Opik MCP fix + pozytywny OAuth E2E.
9. **P19/P20/P21** — PR #39→#52, #45, #49; deploy enrichera; korelacja.
10. **P22/P23/P24** — kompletność, izolacja, digest.
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

- Brak realnego runu Designera po patchu Hindsight (tylko resolver + bezpośredni HTTP).
- Brak nowego merge produktu po naprawie P8 (tylko no-op).
- P17–P24: dane z raportów w toku; sekcje oznaczone „do potwierdzenia”.
- Nie zmieniano Paperclip Core ani nie wykonano żadnego SQL-poza-odczytem.
