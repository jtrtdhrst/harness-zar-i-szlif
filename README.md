# Harness Żar i Szlif — źródła MCP i usługi Coolify

Repozytorium **`jtrtdhrst/harness-zar-i-szlif`** zawiera kod własnych serwerów MCP, gatewayów i integracji Harness. Nie przechowuje kopii źródeł usług, które uruchamiamy z oficjalnych obrazów Docker.

**Katalog obrazów MCP:** [ops/mcp-images/](ops/mcp-images/) — rzeczywiście uruchomione obrazy, wersje GHCR i UUID Coolify.

**Pełny spis:** [ops/coolify-service-registry.json](ops/coolify-service-registry.json) — 36 zasobów Coolify, UUID, właściciel źródła i rzeczywisty status przygotowania kodu. To spis, **nie dowód produkcyjnego wdrożenia**.

## Własne MCP: gdzie jest kod

| Nazwa usługi w Coolify | Katalog w GitHub | Dockerfile | Stan źródła w main |
|---|---|---|---|
| `github-ops-mcp` | [`github-mcp/`](github-mcp/) | `github-mcp/Dockerfile` | Kod + Dockerfile |
| `hermes-gateway` | [`integrations/hermes-paperclip/gateway/`](integrations/hermes-paperclip/gateway/) | `integrations/hermes-paperclip/gateway/Dockerfile` | Kod + Dockerfile |
| `multica-mcp` | [`multica-mcp/`](multica-mcp/) | `multica-mcp/Dockerfile` | Kod + Dockerfile |
| `repowise-deployment-publisher-staging` | [`ops/repowise/`](ops/repowise/) | `ops/repowise/Dockerfile.publisher` | Kod + Dockerfile |
| `hindsight-mcp` | [`hindsight-mcp/`](hindsight-mcp/) | — | PR #132 (niezmergowany) |
| `opik-mcp` | [`opik-mcp/`](opik-mcp/) | — | Kod guard/proxy, backend jako obraz |
| `emailens-mcp` | [`emailens-mcp/`](emailens-mcp/) | `emailens-mcp/Dockerfile` | Kod + Dockerfile |
| `plasmic-mcp` | [`plasmic-mcp/`](plasmic-mcp/) | `plasmic-mcp/Dockerfile` | Kod + Dockerfile |
| `coolify-mcp` | [`coolify-mcp/`](coolify-mcp/) | — | PR #221 (niezmergowany) |
| `qdrant-mcp` | [`qdrant-mcp/`](qdrant-mcp/) | `qdrant-mcp/Dockerfile` | Kod Qdrant w PR #182 (niezmergowany) |
| `supabase-mcp` | [`supabase-mcp/`](supabase-mcp/) | `supabase-mcp/Dockerfile` | Kod + Dockerfile |
| `comfy-mcp` | [`comfy-mcp/`](comfy-mcp/) | `comfy-mcp/Dockerfile` | Kod + Dockerfile |
| `ubuntu-mcp` | [`ubuntu-mcp/`](ubuntu-mcp/) | `ubuntu-mcp/Dockerfile` | Kod + Dockerfile |
| `mantic-mcp` | [`mantic-mcp/`](mantic-mcp/) | `mantic-mcp/Dockerfile.http` | Kod + Dockerfile |
| `playwright-mcp` | [`playwright-mcp/`](playwright-mcp/) | `playwright-mcp/Dockerfile` | Kod + Dockerfile |

**Comfy MCP:** jeden katalog `comfy-mcp/` zawiera teraz pełny kod, Dockerfile, patche i testy. Stary katalog `comfyui-mcp/` usunięto; nazwa pakietu NPM i obecnie używanego obrazu nie musi się zmienić razem z nazwą folderu.

## Gotowe obrazy: bez zbędnych katalogów kodu

- `local-build-registry` — obraz dostawcy; UUID: `g0xdkztpmjnhgwms7qelzxqd`
- `repowise` — zewnętrzne repozytorium; UUID: `oea9obpkhzbgkmipxwqmz2hj`
- `hindsight-core` — obraz dostawcy; UUID: `hjda7ckq5z4luhd1vpdepi0r`
- `opik` — obraz dostawcy; UUID: `s7a4rwqbij7w4fxlnauriblo`
- `mautic` — obraz dostawcy; UUID: `8byf8qjxdixpwp7lsnr8zpto`
- `supabase` — obraz dostawcy; UUID: `r2gnunvpkqwmuew1tupbf7lx`
- `qdrant` — obraz dostawcy; UUID: `eciprwgeyol4znmdd0dpu3xc`
- `opencode` — lokalny obraz, pochodzenie wymaga weryfikacji; UUID: `26aqp0flyvdinjn6dklxnb1c`
- `comfy` — lokalny obraz, pochodzenie wymaga weryfikacji; UUID: `hdn0rl4wznbvaoizna61bbyy`
- `cloudflared-mcp` — obraz dostawcy; UUID: `3byzyvjxsycixyzcpxbujzev`
- `mcp-activation` — obraz dostawcy; UUID: `ra0iy2xs7abgms1r0phx4iqg`
- `outline-knowledge` — obraz dostawcy; UUID: `g16yynrbdpkab4hnmaoj7vxk`
- `multica-stack` — obraz dostawcy; UUID: `6ihjnudsifbcvklz5hqxdldc`
- `multica-edge` — obraz dostawcy; UUID: `vwe5lv4bniosxug34uhyf0ag`
- `repowise-mcp-runtime` — lokalny obraz, pochodzenie wymaga weryfikacji; UUID: `lecwi3emh9hjxir7gphmalie`

Źródła `plasmic/` nadal są kodem modyfikowanego **WAB, nie MCP**. Nie usuwam ich bez przejścia na sprawdzony zamienny obraz. `opik-run-enricher/` to kod telemetryczny, a nie osobny serwer MCP. `mcp-edge/` to istniejący gateway, który musi zostać wycofany osobnym dowodem produkcyjnym. `ops/` zawiera kontrakty wydania, `scripts/` testy i kontrolery, `.github/` pipeline'y, `docs/` dokumentację. Aplikacje `zar-i-szlif-*` należą do repo `jtrtdhrst/zar-i-szlif`.

## Budowanie i wdrażanie

Źródło musi pochodzić z dokładnie przypisanego podfolderu. Wydanie wymaga: review dokładnego SHA → CI/build obrazu → niezmienny digest → autoryzacja release → przypisanie właściwego UUID w Coolify → potwierdzony produkcyjny SHA/digest, autentyczne pozytywne i negatywne E2E oraz możliwość rollback. **Zmiana układu katalogów nie uruchamia sama nowego obrazu produkcyjnego**. Szczegóły: [Harness delivery contract](docs/architecture/HARNESS-DELIVERY-CONTRACT.md).
