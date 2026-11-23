# Qdrant MCP — kompletny kod serwera
UUID Coolify `a4zgmthjspz8hwvyu6llr8dh`. Implementacja: `server.py`, zależności: `requirements.txt`, obraz: `Dockerfile`.

Pliki `server.py` (SHA-256 `59aeaf846aa9781a17a7de098958a4268b145555e948c6f296979356e5b7df45`) i `requirements.txt` (SHA-256 `f7ba36d15d134709fe89125d340299f059b48a671027828f213182b64a9bf101`) są bajtowo identyczne z działającym serwerem produkcyjnym.
Build: `docker build -f mcp/qdrant-mcp/Dockerfile -t qdrant-mcp:staging mcp/qdrant-mcp/`.
Produkcyjny kontener nadal ma stary lokalny obraz `127.0.0.1:5000/harness-qdrant-mcp:deb907a88591`; jego zależność od Git SHA nie została dowiedziona. Dodatni MCP initialize 200 oraz 401 dla złego/brakującego bearer potwierdzono dla starego kontenera, nie nowego.
Nie umieszczać danych kolekcji, tokenów ani Qdrant DB w tym repo.
