# Operations — wydania, mapy i konfiguracja środowiska

**To nie jest kolejna usługa Opik ani drugi katalog kodu MCP.** Z `ops/` korzystają serwery i workery. Kod Opik MCP znajduje się w `mcp/opik-mcp/`, a kod eksportera trace w `workers/opik-run-enricher/`.

- `service-build-roots.json`: ścisła mapa UUID → jedyny root kodu → Dockerfile (kod gotowy ≠ produkcyjny).
- `coolify-service-registry.json`: pełne zasoby Coolify (38 UUID), typ źródła i przypisanie folderu.
- `mcp-images/catalog.json`: faktyczne referencje uruchomionych obrazów, SHA/digest i status potwierdzenia E2E.
- `compose-migration-candidates.json`: **niezatwierdzone** kandydaty do przepięcia Compose.
- `harness/`: mechanizmy admission, credential projection, kontroler i procedury operatora.
- `systemd/`: jednostki i kontrakty usługi, bez przechowywania poświadczeń.
- `audits/`: dowody odczytów, nie uprawnienia do deploy.
**Dla agentów:** `ops/` to inwentarz i kontrakty, nie dowód uruchomionego SHA. Sprawdź bieżące Coolify UUID, `base_directory`, `watch_paths` oraz działający obraz przed deploy. Nie przenoś `ops/` do `mcp/`, nie twórz pustych kopii katalogów obrazów vendor i nie kasuj wolumenów przy migracji źródeł. Zobacz `../AGENTS.md`.

Danych runtime i tokenów nigdy nie zapisujemy w Git.
