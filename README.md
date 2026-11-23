# Żar i Szlif — Harness: serwery MCP i infrastruktura

**Zasada:** kod jednej usługi MCP znajduje się wyłącznie w **`mcp/<nazwa>-mcp/`**. W każdym katalogu jest implementacja, Dockerfile (lub osobne Dockerfile dla składników), testy i opis właściciela wdrożenia. Dane, sekrety, obrazy kontenerów i wolumeny nie trafiają do Git.

## Mapa repo

| Katalog | Co zawiera | Co się tam buduje |
| --- | --- | --- |
| [`mcp/`](mcp/) | **13 serwerów MCP**: kod, Dockerfile, testy, README | Oddzielny OCI obraz na serwer MCP lub jego backend |
| [`gateways/`](gateways/) | Bramka edge dla tras MCP, autoryzacja, ruch HTTP/SSE | Osobne bramki, bez kopiowania kodu MCP |
| [`workers/`](workers/) | Pracownicy asynchroniczni (Opik run enricher) | Worker, nie serwer MCP |
| [`apps/`](apps/) | Plasmic WAB / Studio — aplikacja self-hosted | Wieloskładnikowa aplikacja, nie MCP |
| [`integrations/`](integrations/) | Hermes–Paperclip, gateway, adaptery, testy E2E i historie integracji | Hermes Gateway i integracje agenta |
| [`ops/`](ops/) | Mapa Coolify UUID, katalog obrazów, polityka wydań, systemd, kontrakty i dowody | Konfiguracja i system operacyjny, nie sama aplikacja |
| [`scripts/`](scripts/) | Skrypty CI, testy, selektory buildów, kontrolery wydań | Narzędzia repozytorium |
| [`docs/`](docs/) | Architektura, bieżące runbooki, decyzje, archiwum | Dokumentacja |
| [`.github/workflows/`](.github/workflows/) | Przypisane źródłom workflow CI i publikacji OCI | Build z katalogu wskazanego przez mapę |

## Instrukcje dla agentów i podział usług

**Zacznij od [AGENTS.md](AGENTS.md).** Znajdziesz tam kanoniczne katalogi, zakres odpowiedzialności, sposób weryfikacji produkcji i regułę: kod w repo ≠ wdrożona wersja.

- **Qdrant:** jedyny kod MCP znajduje się w `mcp/qdrant-mcp/`. Dawny główny katalog `qdrant-mcp/` został wycofany — usługa Qdrant MCP, baza i wolumeny produkcyjne pozostają.
- **Opik MCP** (`mcp/opik-mcp/`) przyjmuje autoryzowane żądania narzędzi Opik. **Opik run enricher** (`workers/opik-run-enricher/`) dopisuje bezpieczne metryki do zakończonych trace; to osobny worker, nie drugi serwer MCP.
- **`ops/`** przechowuje mapowanie Coolify, kontrakty wydań i infrastrukturę; nie jest usługą ani katalogiem implementacji MCP. Pliki README i `project.yml` bez kodu nie świadczą o źródłach działającego kontenera.
- **Ścieżki Coolify:** samo przeniesienie kodu do `mcp/` nie zmienia `base_directory` ani `watch_paths` produkcyjnej aplikacji. Agent ma sprawdzić je przed deploymentem, zwłaszcza dla `github-ops-mcp` i `multica-mcp`.

**Szczegóły każdej usługi:** [mcp/README.md](mcp/README.md).
**Architektura i zakres zmian:** [docs/REPOSITORY-ARCHITECTURE.md](docs/REPOSITORY-ARCHITECTURE.md).
**38 Coolify UUID:** [ops/coolify-service-registry.json](ops/coolify-service-registry.json).
**Katalog uruchomionych obrazów i ich pochodzenia:** [ops/mcp-images/](ops/mcp-images/).
**Źródło prawdy dla kontekstów Docker:** [ops/service-build-roots.json](ops/service-build-roots.json).

## Warunek ukończenia (dla każdej usługi oddzielnie)

Dokładny commit źródła → lokalne testy i GitHub CI → OCI image z niezmiennym digestem → niezależny review tego SHA → autoryzowany release → potwierdzenie obraz/digest/katalogu w Coolify → pozytywny i negatywny test MCP/E2E → bezpieczny rollback.

**Ważne:** umieszczenie kodu i zielony Docker build nie oznaczają, że nowy obraz jest już w produkcji. Bieżący obraz każdej usługi należy odczytać z Coolify/Dockera, nie domniemywać go z wersji w Git.
