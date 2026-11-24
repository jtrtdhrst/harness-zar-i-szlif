# Serwery MCP — jeden serwer = jeden katalog kodu

Katalog `mcp/` zawiera tylko serwery MCP i ich kod/proxy bezpieczeństwa. Usługi Qdrant DB, Supabase DB, ComfyUI Engine, Plasmic WAB, Opik Core i Hindsight Core są odrębnymi aplikacjami opartymi na obrazach upstream i **nie** należą do `mcp/`.

| Serwer | Kod i rola | Dockerfile / build root | Coolify UUID | Stan kodu |
| --- | --- | --- | --- | --- |
| [comfy-mcp](comfy-mcp/) | Sterowanie ComfyUI, narzędzia obrazu, integracja plików | `mcp/comfy-mcp/Dockerfile` | `kkhfw0napmeaqewgdirwhc1h` | Kod w repo; produkcja nadal ma obraz lokalny |
| [coolify-mcp](coolify-mcp/) | Operacje Coolify, OAuth, MCP HTTP | `mcp/coolify-mcp/Dockerfile` | `f7smgdueq8frlex9lfhp9iji` | Pełny kod v3.10.1; produkcja na obrazie Harness ze źródłową etykietą `b0bb233c`, health PASS; nowy układ katalogów nadal przed wydaniem |
| [emailens-mcp](emailens-mcp/) | Emailens MCP Bridge, zabezpieczenia i testy HTTP | `mcp/emailens-mcp/Dockerfile` | `16qnapdkj0qqqmeokepdechk` | Kod w repo; produkcja używa wcześniejszego digestu |
| [github-mcp](github-mcp/) | GitHub Ops MCP z kontrolą operacji | `mcp/github-mcp/Dockerfile` | `t09dqe2eppn2eiqmhzlf8xzp` | Kod w repo, Git-backed app |
| [hindsight-mcp](hindsight-mcp/) | Bramka Caddy/Hindsight, izolacja banków | `mcp/hindsight-mcp/Dockerfile` | `aglen8ervlo2lpi30oz8iii9` | Produkcyjny Caddyfile + osobny nieaktywny wariant PR #132 |
| [mantic-mcp](mantic-mcp/) | Operacje Mautic (kontakty, kampanie) przez MCP | `mcp/mantic-mcp/Dockerfile.http` | `bioufw4uxwuhmr51ueyahf0u` | Kod w repo |
| [multica-mcp](multica-mcp/) | Native MCP interfejs orkiestratora Multica | `mcp/multica-mcp/Dockerfile` | `5o4edyfjo0wftfg08mtkknir` | Kod w repo, Git-backed app |
| [opik-mcp](opik-mcp/) | Backend Opik MCP + Access JWT guard + Nginx proxy | `mcp/opik-mcp/backend/Dockerfile`, `access-guard/Dockerfile` | `egasedqaofxnzcqppuxi805h` | Kod backendu odzyskany z działającego obrazu lokalnego; brak potwierdzonego Git SHA upstream |
| [plasmic-mcp](plasmic-mcp/) | 42+ narzędzia MCP dla Plasmic WAB | `mcp/plasmic-mcp/Dockerfile` | `a6ci2beifbinzckfnneiqnjd` | Kod w repo |
| [playwright-mcp](playwright-mcp/) | Browser MCP, zarządzanie sesjami i idle proxy | `mcp/playwright-mcp/Dockerfile` | `9e4fzsodixl4qzzap4zg0ntp` | Kod w repo |
| [supabase-mcp](supabase-mcp/) | MCP do operacji Supabase, RLS i storage | `mcp/supabase-mcp/Dockerfile` | `tjit4c8m0kjh8brkmdhyvkde` | Kod w repo |
| [ubuntu-mcp](ubuntu-mcp/) | Administracja Ubuntu/SSH i audyt z rolami | `mcp/ubuntu-mcp/Dockerfile` | `lcnjb3vreec7saihkhan6akh` | Kod w repo |

**Budowanie:** `docker build -f mcp/playwright-mcp/Dockerfile -t test-playwright mcp/playwright-mcp/`. Nie wolno budować danego MCP z korzenia repo `.` ani mieszać plików źródłowych różnych usług.

**Źródła i obrazy to różne rzeczy:** [ops/mcp-images/catalog.json](../ops/mcp-images/catalog.json) zapisuje rzeczywiste obrazy i UUID; jeśli brak niezależnie potwierdzonego manifest digest/SHA, wydanie pozostaje niezweryfikowane.

**Historia migracji:** Qdrant MCP został całkowicie wycofany ze źródeł w PR #182 i z konfiguracji bramy w PR #234. Nie przywracaj jego katalogu ani wpisu buildowego. Osobna baza danych Qdrant pozostaje aktywna. Hindsight MCP (PR #132) jest oddzielnym komponentem i zachowuje swoje niezależne sekrety i dane.

## Production migration evidence — 2026-11-24

Target: protected GitHub main → reviewed source-specific change → native Coolify automatic build → production health and functional acceptance → verified rollback. This is a point-in-time operator observation, not a release authorization or completion claim. GitHub main observed: `e44952c97397f78fc47e8062793b4f8fc9ece1bc`.

| MCP | Production resource | Observed delivery status | Next gate |
| --- | --- | --- | --- |
| Multica | Application | HEAD, main, autodeploy enabled; current production image parity unverified | Reviewed push-triggered production delivery and E2E |
| GitHub | Application | HEAD, main, autodeploy enabled; parallel immutable runtime exists | PR #204, exact source/live route, E2E |
| Comfy | Service | Local image; Git candidate stopped | Reviewed endpoint-preserving cutover |
| Coolify | Service | Existing GHCR image; candidate build from main succeeded, runtime failed and rolled back | PR #245, scoped runtime configuration and persistent OAuth state |
| Emailens | Service | Existing registry digest; Git candidate stopped | Reviewed configuration-preserving cutover |
| Hindsight | Service | Caddy gateway; Git migration pending | PR #132 conflicts; preserve bank isolation |
| Mantic | Service | Stopped | Respect intentional stop; reconcile migration disposition |
| Opik | Service | Local images and multiple components; candidates stopped | PR #241 and reviewed multi-component cutover |
| Plasmic | Service | Existing registry digest; candidate stopped | Preserve WAB access and persistent state |
| Playwright | Service | Existing registry tag | PR #232 and verified session isolation |
| Supabase | Service | Existing registry digest; candidate stopped | Reviewed configuration-preserving cutover |
| Ubuntu | Service | Existing registry digest; candidate stopped | Preserve existing authorization boundaries |
| RepoWise | Service + application | Full upstream source vendored under `apps/repowise/` by merged PR #235; runtime still uses upstream-backed delivery | ZARI-274/286, PR #196; resolve canonical MCP transport source and exact production mapping |

The retired Qdrant MCP is excluded; the separate Qdrant database is not a MCP service. RepoWise is not yet a canonical folder under `mcp/` on the observed main. Cloudflare/cloudflared are outside this migration.

Coolify candidate deployment `l7krpcvsgj6vvxuayg3i9ugu`: native build passed from observed main; runtime failed due to missing scoped environment and non-root OAuth state directory permissions. Coolify rolled back the candidate. PR #245 fixes the directory; independent review, merge and functional E2E remain outstanding. Do not report this as a production release.

At the observation time: 2/13 production Git-backed configurations had auto-deploy enabled; 0/13 had complete verified E2E receipts. RepoWise `list_repos` returned the same main SHA for the Harness index, but semantic retrieval was degraded and answer synthesis timed out; direct-path documentation retrieval succeeded. Index freshness is distinct from retrieval quality and runtime deployment truth.

Authoritative execution record: [ZARI-298](https://multica.zariszlif.pl/zar-i-szlif/issues/01a20e3a-94d1-76c7-9b67-95c38102b667). Update this ledger from actual GitHub/Coolify/VPS evidence, never by marking a pending migration as complete. See [delivery contract](../docs/architecture/HARNESS-DELIVERY-CONTRACT.md).
