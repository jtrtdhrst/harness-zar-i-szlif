# Opik MCP backend — produkcyjna kopia źródeł
W archiwum dzielonym na części `source-parts/part-*` umieszczono kod modułu Pythona faktycznie zainstalowany w działającym kontenerze `opik-mcp-egasedqaofxnzcqppuxi805h` (22.11.2026); **nie są to sekrety ani pliki konfiguracji użytkownika**.
Oryginalny pakiet `opik-mcp 3.0.7.dev0`, licencja Apache-2.0, upstream https://github.com/comet-ml/opik-mcp. `requirements.lock` odczytano z tego samego środowiska Python 3.13. Sposób instalacji produkcyjnej: `file:///app`, dlatego dokładny Git SHA oryginału nie został ustalony.
`Dockerfile` buduje odtwarzalny kandydat backendu bez przenoszenia poświadczeń. Do kompletnego wdrożenia Opik MCP są jeszcze potrzebne osobne obrazy access-guard i Nginx proxy, zachowanie istniejących reguł OAuth/Cloudflare i testy produkcyjne.
Nie uznawać tego za produkcyjny upgrade, dopóki nie zostaną porównane wersja, funkcje, środowisko, immutable digest i autoryzowany E2E.

Źródło jest pakowane jako jeden zweryfikowany snapshot uruchomionego modułu Python (po wypakowaniu `opik_mcp/`), aby nie utrzymywać setek niezmienionych kopii kodu upstream jako własnych commitów. Przywrócenie i lista plików: `cat source-parts/part-* > opik-mcp-runtime-src.tar.xz && tar -tJf opik-mcp-runtime-src.tar.xz`. Nie jest to skompilowany obraz Dockera.

Integralność: `source-parts/ARCHIVE.sha256` zawiera SHA-256 połączonego archiwum. Dockerfile weryfikuje ten hash **przed** rozpakowaniem. Podział na osiem części jest wyłącznie transportową reprezentacją jednej paczki z produkcji, nie ośmioma wersjami kodu.
