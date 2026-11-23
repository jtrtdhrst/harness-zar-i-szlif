# Workers — zadania wykonywane poza serwerami MCP
- `opik-run-enricher/`: Python worker korelujący audytowane wykonania agentów z trace Opik (bez surowych promptów i sekretów).
- Dockerfile i testy znajdują się bezpośrednio w folderze workera. Nie przypisywać mu UUID serwera Opik MCP.
