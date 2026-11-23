# Scripts — testy, selektory i kontrolery
- `select_mcp_builds.py` buduje tylko zmieniony serwer `mcp/<nazwa>/`; `select_owned_runtime_builds.py` obsługuje własne aplikacje/gatewaye.
- `test_*.py` zawiera regresje bezpieczeństwa, izolacji, polityki wydań i map katalogów.
- `check-release-lanes.py` i `harness_release_admission.py` pozostają natywną ścieżką kontroli wydania. Nie omijać HOLD ani approval.
- `check_service_coverage.py` pilnuje podziału katalogów najwyższego poziomu; mapa `ops/service-build-roots.json` kontroluje źródła usług wewnątrz `mcp/`.
