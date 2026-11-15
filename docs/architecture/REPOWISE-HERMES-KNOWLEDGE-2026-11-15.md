# RepoWise + Hermes Gateway — stan wiedzy agentów (2026-11-15)

Snapshot po naprawie jakości indeksu RepoWise i podłączeniu go do Hermes Gateway.
Dokument opisuje stan zastany i wykonane zmiany; nie jest deklaracją runtime.

## 1. Co naprawiono w RepoWise (0.60.1)

| Problem (stan 2026-11-13) | Zmiana | Dowód |
|---|---|---|
| `model_name` pusty na 288/288 stronach harness i 132/132 product — wiki była w całości szablonowa | `repowise generate --unwritten -y --cascade none --page <id>`, jeden proces na stronę | strony `module_page`/`flow_page`/`onboarding`/`repo_overview` mają `model_name = deepseek-v4.1-flash` |
| wektory w LanceDB z `mock` (status `"embedder": "mock"`) — semantic search działał tylko przez FTS | `repowise reindex --embedder openai` (qwen3.7, 1024 dims, przez `opencode-go-proxy`) | 292 wektory harness, 134 product; `sources` w `search_codebase` zawiera `vector` |
| `sync-from-github.sh` promował indeks zbudowany `--network none`, więc do live trafiały wektory mock | po promocji i smoke testach: `reindex --embedder openai` per repo | krok w `sync-from-github.sh` (backup `.bak-20261115-pregenerate`) |
| batch `generate --unwritten` wieszał się na pojedynczej stronie i blokował resztę | `refill-pages.sh` + `refill-all.sh` + `repowise-generate.timer` (co 30 min, flock, `timeout 420` na stronę) | `unwritten.py` zwraca listę stron do dopisania; timer domyka braki po sync |

Konfiguracja runtime (poza Git): `.repowise/config.yaml` ma `max_tokens: 32768`; domyślne 16384 ucinało duże strony i kończyło się `stub_fallback`.

## 2. Hermes Gateway

Kontener `yh20mb2rurecnmn60t5vfc3s-20261106T181437`, Hermes `0.22.5`, profil `default`, API `http://127.0.0.1:8642/v1`.

- `mcp_servers.repowise`: `http://repowise-mcp:7338/mcp`, nagłówek `Authorization: Bearer $REPOWISE_API_KEY`, `timeout 120`.
- Model: `deepseek-v4.1-flash`, `provider: custom`, `base_url: http://opencode-go-proxy:8799/zen/go/v1`, `api_key: ${OPENAI_API_KEY}` (`/opt/data/.env`). Wcześniej gateway nie miał żadnego providera i każdy run kończył się `agent_error`.
- Polityka: blok `## Knowledge tools (mandatory)` w `/opt/data/SOUL.md` — RepoWise przed `grep`; świeżość = `head` zgodny z GitHub main i `commits_behind == 0`, nie wiek `indexed_at`; RepoWise nie jest dowodem runtime.

Backupy: `config.yaml.bak-20261115-repowise`, `SOUL.md.bak-20261115`.

## 3. Granice źródła

- RepoWise indeksuje **kod** (pliki, symbole, graf, historia, decyzje, health, doc-drift). Nie tworzy stron z `docs/**` w trybie `deterministic` — dokumentacja pozostaje w Git/GitHub, nie w MCP.
- RepoWise nie jest dowodem wdrożenia: `indexed_commit == live_head` potwierdza zgodność indeksu z GitHub, nie stan kontenera.
- Hindsight pozostaje jedynym miejscem na zweryfikowane doświadczenie wykonawcze; polityka: 1 `recall` na start, 1 `retain` po potwierdzonym wyniku.

## 4. Weryfikacja

```bash
# świeżość i zawartość indeksu
docker exec repowise-mcp-lecwi3emh9hjxir7gphmalie repowise status --workspace --format json
# kluczowe pola: indexed=true, stale=false, commits_behind=0, head=<GitHub main>

# Hermes widzi narzędzia
docker exec -u hermes -e HOME=/opt/data yh20mb2rurecnmn60t5vfc3s-20261106T181437 \
  /opt/hermes/.venv/bin/hermes mcp test repowise   # 16 narzędzi

# E2E: pytanie o kod przez gateway
curl -s -H "Authorization: Bearer $API_SERVER_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"hermes-agent","stream":false,"messages":[{"role":"user","content":"Use RepoWise: which file classifies release lanes?"}]}' \
  http://127.0.0.1:8642/v1/chat/completions
```

Wynik canary 2026-11-15: agent wywołał `list_repos` + `search_codebase`/`get_context`, podał SHA `bf38352a`/`6ed8bcfe`, plik `scripts/release-targets.mjs` i lane'y `frontend/cloudflare/mcp/www/website` + fallback `code`.

## 5. Otwarte

- Pełna proza RepoWise wymaga `init --prose` (koszt); obecnie model pisze tylko strony koncepcyjne, reszta jest szablonowa.
- PR `#106` przenosi dwa ADR z live mirror do Git; do merge sync może paść na `source-dirty-overlap`, jeśli commit dotknie `.repowise/decisions.yaml`.
- RepoWise nie indeksuje treści `docs/**`; agenci czytają dokumentację z checkoutu/GitHub.
