# Operations — wydania, mapy i konfiguracja środowiska
- `service-build-roots.json`: ścisła mapa UUID → jedyny root kodu → Dockerfile (kod gotowy ≠ produkcyjny).
- `coolify-service-registry.json`: pełne zasoby Coolify (36 UUID), typ źródła i przypisanie folderu.
- `mcp-images/catalog.json`: faktyczne referencje uruchomionych obrazów, SHA/digest i status potwierdzenia E2E.
- `compose-migration-candidates.json`: **niezatwierdzone** kandydaty do przepięcia Compose.
- `harness/`: mechanizmy admission, credential projection, kontroler i procedury operatora.
- `systemd/`: jednostki i kontrakty usługi, bez przechowywania poświadczeń.
- `audits/`: dowody odczytów, nie uprawnienia do deploy.
Danych runtime i tokenów nigdy nie zapisujemy w Git.
