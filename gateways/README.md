# Gateways — routing i bezpieczeństwo
- `mcp-edge/`: kod HTTP/SSE Worker i proxy MCP (Cloudflare Workers + osobny Coolify edge), testy i deklaracje tras.
- Nie przechowuje implementacji providerów MCP ani sekretów. Przy każdej zmianie wymagane testy autoryzacji oraz negatywne testy tras.
- W produkcji nie nadpisuj istniejącego ruchu przez sam merge kodu.
