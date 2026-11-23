# Hindsight MCP — konfiguracja działającej bramki + kandydat
UUID Coolify `aglen8ervlo2lpi30oz8iii9`.
- `Caddyfile` jest bajtową kopią **działającej produkcyjnej** konfiguracji `/etc/caddy/Caddyfile` z 22.11.2026; SHA-256 `ef90edbd744c6839416272652215130a79008729e1297746cb86b3b2994d34b8`.
- `Dockerfile` i `.dockerignore` zostały odzyskane z istniejącego PR #132.
- `Caddyfile.proposed-14-banks` zachowuje niescalony wariant rozszerzający rozdzielenie banków; ten plik **nie** jest używany w domyślnym buildzie ani na produkcji.
- `compose.candidate.yml` jest nadal wyłącznie kandydatem. Bez uwierzytelnionych testów cross-bank/ACL i formalnej autoryzacji nie przestawiać Coolify.
Build: `docker build -f mcp/hindsight-mcp/Dockerfile -t hindsight-mcp:staging mcp/hindsight-mcp/`.
