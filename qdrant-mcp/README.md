# Qdrant MCP — kod źródłowy i własny obraz

- Coolify UUID: `a4zgmthjspz8hwvyu6llr8dh`.
- **Kod w tym folderze:** `server.py`, `requirements.txt`, `Dockerfile`.
- Odpowiada plikom odczytanym z produkcyjnego kontenera; SHA-256 w [katalogu obrazów](../ops/mcp-images/catalog.json).
- Build: `docker build -f qdrant-mcp/Dockerfile -t qdrant-mcp:test qdrant-mcp/`.
- Produkcja obecnie korzysta ze starszego `127.0.0.1:5000/harness-qdrant-mcp:deb907a88591`, a jego związek z Git SHA nie jest potwierdzony.
- Dane bazy Qdrant są osobne; nie przechowuj ich ani sekretów w repo. Qdrant engine używa obrazu dostawcy, a nie folderu `qdrant/`.
