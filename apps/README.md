# Apps — samodzielne aplikacje, nie serwery MCP
- `plasmic/`: samohostowana platforma Plasmic WAB/Studio wraz z submodułem upstream; osobne obrazy/DB, niezależne wydanie.
- Kod adaptera do Plasmic MCP znajduje się wyłącznie w `../mcp/plasmic-mcp/`.
- Produkcyjne obrazy Plasmic WAB, codegen i studio wymagają osobnego planu migracji i weryfikacji danych.
