# AGENTS.md — Harness Żar i Szlif

To repozytorium zawiera **kod własnych integracji MCP oraz konfigurację ich uruchamiania**. Nie jest kopią całego środowiska Coolify, katalogiem danych Docker ani repozytorium produktu `jtrtdhrst/zar-i-szlif`. Zanim zmienisz kod, odczytaj bieżący `main`, przypisane zadanie Multica, istniejący PR i aktualny stan Coolify. Ten dokument opisuje organizację kodu — **nie nadaje uprawnień agenta ani zgody na release**.

## Gdzie agent ma pracować

| Ścieżka | Odpowiedzialność | Reguła |
| --- | --- | --- |
| `mcp/<usługa>/` | Jedyny kanoniczny kod serwera MCP, Dockerfile, zależności i testy | Jeden MCP = jeden folder; build context tego folderu |
| `gateways/mcp-edge/` | Transport, proxy, routing i uwierzytelnienie edge | Nie duplikuj implementacji narzędzi MCP |
| `workers/opik-run-enricher/` | Worker wzbogacający ukończone ślady Opik | Nie jest serwerem MCP ani drugim Opik |
| `apps/plasmic/` | Osobna wielokomponentowa aplikacja Plasmic WAB | Nie przenoś jej do `mcp/` |
| `integrations/hermes-paperclip/` | Gateway Hermes, adaptery Multica/Paperclip, testy integracyjne | Zachowaj task-scoped runtime i izolację |
| `ops/` | UUID i mapy Coolify, kontrakty release, obrazy, systemd, dowody | **Konfiguracja operacyjna, nie kod kolejnego MCP** |
| `scripts/` | Skrypty testowe, walidacyjne, CI/release tooling | Nie tworzyć alternatywnego kontrolera wydawania |
| `docs/` | Architektura, decyzje i instrukcje | Nie traktować starych runbooków jako żywego stanu |
| `.github/workflows/` | Build i testy zależne od katalogów | Każdy selector musi odpowiadać kanonicznym ścieżkom |

## Opik: dlaczego dwa katalogi

- `mcp/opik-mcp/`: backend Opik MCP (`backend/`), kontrola dostępu JWT (`access-guard/`) i prywatny proxy (`proxy/`). **Przyjmuje** autoryzowane wywołania narzędzi Opik. Obecna produkcja jest usługą Coolify `egasedqaofxnzcqppuxi805h` z lokalnymi obrazami; kod odtworzony w repo nie oznacza automatycznego przestawienia obrazów.
- `workers/opik-run-enricher/`: niezależny proces batch. **Wysyła** do istniejących trace w Opik dozwolone metryki/zliczenia z zakończonych przebiegów agentów oraz Hindsight, bez surowych logów, promptów i treści pamięci. Nie obsługuje `tools/list` ani `tools/call`. W odczytanej liście 36 zasobów Coolify (2026-11-23) nie ma osobnego zasobu o tej nazwie — nie zakładaj wdrożenia, sprawdź rzeczywistego operatora przed zmianą.
- `ops/` to wspólna infrastruktura dla **wszystkich** integracji. Nie jest drugą implementacją Opik; `ops/mcp-images/catalog.json` przechowuje inwentaryzację obrazów, a nie skompilowany serwer.

## Qdrant: tylko jeden katalog źródeł

`mcp/qdrant-mcp/` zawiera `server.py`, `requirements.txt`, `Dockerfile`, README i kontrakty. Dawny katalog główny `qdrant-mcp/` zawierał jedynie dokumentację i kandydackie kontrakty Compose. Po migracji nie wolno go odtwarzać. **Nie usuwać** usługi Coolify `a4zgmthjspz8hwvyu6llr8dh`, obrazu produkcyjnego, Qdrant DB ani wolumenów/zbiorów danych w ramach porządkowania repo.

## Procedura zmiany dla każdego agenta

1. Otwórz przypisane istniejące zadanie Multica i powiązany PR; sprawdź, czy inny writer nie pracuje nad tym samym zakresem. Zakres zapisu określają realne uprawnienia, zadanie i aktywne HOLD — nigdy tylko ten dokument.
2. Zidentyfikuj właściwy `root` i `dockerfile` po `ops/service-build-roots.json` oraz rzeczywisty UUID po `ops/coolify-service-registry.json`. Dla usług typu `vendor-image`, `upstream-git`, `other-repository` lub `local-image-unknown-source` **nie twórz pustego folderu udającego źródła**.
3. Przed zmianą katalogu porównaj rzeczywistą produkcyjną ścieżkę `base_directory`, `watch_paths`, `dockerfile_location`, Compose, SHA i obraz/digest. Na 2026-11-23 aplikacje `github-ops-mcp` i `multica-mcp` nadal używają w Coolify starych ścieżek `/github-mcp` oraz `/multica-mcp`; kanoniczne cele to `/mcp/github-mcp` i `/mcp/multica-mcp`. Nie uruchamiaj deploy, zanim nie zostanie wykonany autoryzowany cutover konfiguracji.
4. Zmień minimalny zakres, uruchom testy pozytywne i negatywne oraz dokładne CI dla SHA; jeden task ma maksymalnie jeden kanoniczny branch/PR. Nie zmieniaj poza zakresem kodu, sekretów, danych i wolumenów.
5. Osobno sprawdź niezależny CTO review dokładnego HEAD, zgodę COO/release zgodną z istniejącym HOLD ZARI-213, niezmienny digest OCI, stan deploymentu w Coolify, zgodność obrazu na produkcji i działające uwierzytelnione/odrzucone E2E. Merge lub zdrowy kontener to **nie** dowód DONE. Dla każdego nieosiągniętego etapu zwróć `NOT_DONE` z konkretnym dowodem.

## Szybkie źródła prawdy

- `README.md` oraz `docs/REPOSITORY-ARCHITECTURE.md`: mapa architektury.
- `mcp/README.md`: lista i przeznaczenie 13 serwerów MCP.
- `ops/coolify-service-registry.json`: mapa 36 zasobów Coolify z odczytu 2026-11-22; weryfikuj ponownie przed akcją.
- `ops/service-build-roots.json`: 16 katalogów własnego kodu i konfiguracja budowania.
- `ops/mcp-images/catalog.json`: migawka obrazów, **nie atestacja** aktualnej produkcji.
- `workers/opik-run-enricher/README.md` i `mcp/opik-mcp/README.md`: dwa niezależne procesy Opik.

Nigdy nie umieszczaj w repo tokenów, prawdziwych envów, bazy danych, zawartości wolumenów, prywatnych logów ani zrzutów sekretów. Nie usuwaj usług produkcyjnych jako skutku porządków struktury repo.
