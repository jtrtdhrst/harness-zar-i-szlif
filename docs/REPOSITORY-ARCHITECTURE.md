# Architektura źródeł, kontenerów i usług Coolify

## Po co ta migracja?
Historyczny korzeń repo zawierał 13 katalogów `*-mcp`, niezależne WAB, proxy edge, workery, integracje i skrypty. To prowadziło do błędnych założeń, że plik `project.yml` jest kompletną implementacją MCP. Po migracji kod i Dockerfile jednego serwera znajdują się w `mcp/<nazwa>/`. W katalogu głównym nie ma przypadkowych bliźniaczych nazw.

## Warstwy
1. `mcp/` — serwery i kod źródłowy; każdy ma UUID, Dockerfile, zależności, testy i README.
2. `gateways/` — reverse proxy, worker edge, transport i autoryzacja. Nie implementują narzędzi providera.
3. `workers/` — asynchroniczna telemetria i przetwarzanie; nie wystawiają endpointu MCP.
4. `apps/` — aplikacje (np. Plasmic WAB) z własnym cyklem wydawniczym i DB.
5. `integrations/` — Hermes/Paperclip, adaptery i ich E2E, oddzielone od adapterów MCP.
6. `ops/` — podpisane wydania, katalog obrazów, zmienne źródła, systemd; `scripts/` — implementacja testów i kontrolerów.
7. `docs/` — instrukcje i historia; `.github/workflows/` — deklaracje CI.

## Źródła odzyskane z działającego Coolify
- **Qdrant MCP — HISTORYCZNE / WYCOFANE:** wcześniejsze kopie `server.py`, `requirements.txt` i Dockerfile służyły wyłącznie odtworzeniu stanu. PR #182 usunął katalog i build, a PR #234 wycofał trasę bramy. Nie traktować tego wpisu jako instrukcji wdrożenia. Oddzielna baza Qdrant i jej dane nadal działają.
- **Hindsight MCP:** domyślny `Caddyfile` identyczny bajtowo z /etc/caddy/Caddyfile działającego kontenera (ef90edbd744c6839416272652215130a79008729e1297746cb86b3b2994d34b8). Osobno `Caddyfile.proposed-14-banks` z PR #132; **nie należy go przypadkowo wdrożyć**.
- **Opik MCP:** kod Pythona vendored ze zainstalowanego modułu `opik_mcp` w `local/opik-mcp:3.0.7`; metadata `opik-mcp 3.0.7.dev0`, Apache-2.0 i lock 38 pakietów. Origin upstream https://github.com/comet-ml/opik-mcp. Dokładny oryginalny Git commit nie był dostępny w kontenerze (`direct_url=file:///app`). Istniejąca bramka OAuth/NGINX jest zachowana bez zmiany sekretów.
- **Coolify MCP:** PR #221 został scalony do `main`; produkcja została niezależnie od tego PR przełączona na `ghcr.io/jtrtdhrst/coolify-mcp@sha256:3680d1b58fbc6c5097ac3f525e9e1b0aaec390be0a05ab5580eba322f70d734d`, `org.opencontainers.image.revision=b0bb233c2c6ca5c1a81c38d80aa75d3fd9f9c4b9` (odczyt Docker 22.11.2026). Kontener `running:healthy`, zachowany wolumen `/data`, poprzedni bind `/app/dist/lib/oauth.js` nie występuje. To dowód uruchomionego obrazu i etykiety, NIE zatwierdzonego E2E nowego katalogu `mcp/coolify-mcp/` ani niezależnej atestacji SHA→OCI digest.
- **Pozostałe MCP:** wcześniej własne źródła w rootach repo; wszystkie przeniesione bez zmiany treści produkcyjnych obrazów i wolumenów.

## Co oznacza DONE?
`CODE_PRESENT`: plik i Dockerfile w repo. `BUILD_PASS`: CI Docker z dokładnego SHA. `PUBLISHED`: immutable OCI manifest digest w registry. `DEPLOYED`: odczyt tego samego digest w Coolify konkretnym UUID. `E2E_PASS`: uprawniony klient wykonuje rzeczywistą funkcję, a nieuprawniony jest odrzucany. Dopiero wszystkie wymagane etapy oraz rollback dają `DONE`.

## Zasady migracji ścieżek
- `mcp/<nazwa>/` to build context dla serwera, nigdy `.`.
- GitHub workflow `paths`, matrix source root, Dockerfile i Coolify base_directory muszą być zgodne.
- W `ops/mcp-images/catalog.json` pozostają dowody starych obrazów. Nie usuwać historycznych obrazów używanych przez działające kontenery.
- Nie wolno automatycznie merge/deploy omijając aktywny HOLD ZARI-213, niezależny CTO review lub COO release authorization.
- Zmiana ścieżki kodu nie wymusza restartu usługi w Coolify przed wydaniem.
