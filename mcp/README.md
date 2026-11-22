# Serwery MCP — jeden serwer = jeden katalog kodu

Katalog `mcp/` zawiera tylko serwery MCP i ich kod/proxy bezpieczeństwa. Usługi Qdrant DB, Supabase DB, ComfyUI Engine, Plasmic WAB, Opik Core i Hindsight Core są odrębnymi aplikacjami opartymi na obrazach upstream i **nie** należą do `mcp/`.

| Serwer | Kod i rola | Dockerfile / build root | Coolify UUID | Stan kodu |
| --- | --- | --- | --- | --- |
| [comfy-mcp](comfy-mcp/) | Sterowanie ComfyUI, narzędzia obrazu, integracja plików | `mcp/comfy-mcp/Dockerfile` | `kkhfw0napmeaqewgdirwhc1h` | Kod w repo; produkcja nadal ma obraz lokalny |
| [coolify-mcp](coolify-mcp/) | Operacje Coolify, OAuth, MCP HTTP | `mcp/coolify-mcp/Dockerfile` | `f7smgdueq8frlex9lfhp9iji` | Pełny kod v3.10.1 (PR #221 scalony), produkcja 3.9.0 upstream |
| [emailens-mcp](emailens-mcp/) | Emailens MCP Bridge, zabezpieczenia i testy HTTP | `mcp/emailens-mcp/Dockerfile` | `16qnapdkj0qqqmeokepdechk` | Kod w repo; produkcja używa wcześniejszego digestu |
| [github-mcp](github-mcp/) | GitHub Ops MCP z kontrolą operacji | `mcp/github-mcp/Dockerfile` | `t09dqe2eppn2eiqmhzlf8xzp` | Kod w repo, Git-backed app |
| [hindsight-mcp](hindsight-mcp/) | Bramka Caddy/Hindsight, izolacja banków | `mcp/hindsight-mcp/Dockerfile` | `aglen8ervlo2lpi30oz8iii9` | Produkcyjny Caddyfile + osobny nieaktywny wariant PR #132 |
| [mantic-mcp](mantic-mcp/) | Operacje Mautic (kontakty, kampanie) przez MCP | `mcp/mantic-mcp/Dockerfile.http` | `bioufw4uxwuhmr51ueyahf0u` | Kod w repo |
| [multica-mcp](multica-mcp/) | Native MCP interfejs orkiestratora Multica | `mcp/multica-mcp/Dockerfile` | `5o4edyfjo0wftfg08mtkknir` | Kod w repo, Git-backed app |
| [opik-mcp](opik-mcp/) | Backend Opik MCP + Access JWT guard + Nginx proxy | `mcp/opik-mcp/backend/Dockerfile`, `access-guard/Dockerfile` | `egasedqaofxnzcqppuxi805h` | Kod backendu odzyskany z działającego obrazu lokalnego; brak potwierdzonego Git SHA upstream |
| [plasmic-mcp](plasmic-mcp/) | 42+ narzędzia MCP dla Plasmic WAB | `mcp/plasmic-mcp/Dockerfile` | `a6ci2beifbinzckfnneiqnjd` | Kod w repo |
| [playwright-mcp](playwright-mcp/) | Browser MCP, zarządzanie sesjami i idle proxy | `mcp/playwright-mcp/Dockerfile` | `9e4fzsodixl4qzzap4zg0ntp` | Kod w repo |
| [qdrant-mcp](qdrant-mcp/) | Python MCP hybrid search + CRUD | `mcp/qdrant-mcp/Dockerfile` | `a4zgmthjspz8hwvyu6llr8dh` | Kod bajtowo zgodny z działającym kontenerem |
| [supabase-mcp](supabase-mcp/) | MCP do operacji Supabase, RLS i storage | `mcp/supabase-mcp/Dockerfile` | `tjit4c8m0kjh8brkmdhyvkde` | Kod w repo |
| [ubuntu-mcp](ubuntu-mcp/) | Administracja Ubuntu/SSH i audyt z rolami | `mcp/ubuntu-mcp/Dockerfile` | `lcnjb3vreec7saihkhan6akh` | Kod w repo |

**Budowanie:** `docker build -f mcp/playwright-mcp/Dockerfile -t test-playwright mcp/playwright-mcp/`. Nie wolno budować danego MCP z korzenia repo `.` ani mieszać plików źródłowych różnych usług.

**Źródła i obrazy to różne rzeczy:** [ops/mcp-images/catalog.json](../ops/mcp-images/catalog.json) zapisuje rzeczywiste obrazy i UUID; jeśli brak niezależnie potwierdzonego manifest digest/SHA, wydanie pozostaje niezweryfikowane.

**Historia migracji:** PR #182 i PR #132 były źródłami kodu dla Qdrant i Hindsight. Żaden automatyczny release nie wynika z przeniesienia tych plików. Sekrety OAuth i dane banków Hindsight pozostają po stronie Coolify.
