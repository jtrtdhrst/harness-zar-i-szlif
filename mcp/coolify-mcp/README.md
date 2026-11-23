# coolify-mcp

> **Źródło tej usługi Coolify:** repo `jtrtdhrst/harness-zar-i-szlif`, UUID `f7smgdueq8frlex9lfhp9iji`; katalog `mcp/coolify-mcp/`; Dockerfile `mcp/coolify-mcp/Dockerfile (PR #221 scalony)`; implementacja: `src/ (PR #221 scalony)`.
> Kod pełnego serwera jest jeszcze w istniejącym PR #221, nie w main.


Coolify project/service folder. Runtime data volumes are owned by this
project; only `volumes/` markers are committed.

- Project metadata: `project.yml`
- Runtime source/image: see `docs/COOLIFY-PROJECTS.md`
- No secrets or runtime data in Git.

**Odczyt produkcji 22.11.2026:** kontener healthy na `ghcr.io/jtrtdhrst/coolify-mcp@sha256:3680d1b58fbc6c5097ac3f525e9e1b0aaec390be0a05ab5580eba322f70d734d`, image source revision `b0bb233c2c6ca5c1a81c38d80aa75d3fd9f9c4b9`; obecny po merge folder `mcp/coolify-mcp/` pozostaje jeszcze niezweryfikowany jako osobny produkcyjny build. Wolumen `/data` zachowany i legacy OAuth file bind nie występuje. Nie utożsamiać obrazu z etykietą SHA z niezależnym E2E.
