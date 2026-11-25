# Katalog obrazów MCP (Docker OCI)

Jedno miejsce: **[catalog.json](catalog.json)**. Obejmuje 19 zasobów MCP/gateway odczytanych z aktualnej mapy Coolify. Każdy ma UUID, katalog źródłowy, Dockerfile (gdy istnieje), referencję uruchomionego obrazu, ID obrazu i historię zweryfikowanych buildów GHCR.

**Źródła:** kod serwera jest w jego folderze (`mcp/playwright-mcp/`, `mcp/opik-mcp/` itd.). **Obrazy:** warstwy binarne pozostają w rejestrach OCI (GHCR, lokalny registry lub rejestr producenta). Nie zapisujemy wielogigabajtowych tarballi w repozytorium Git.

**Jak czytać dowody:** `last_published_ghcr_tag` pochodzi z zakończonego powodzeniem joba budowania i push na SHA `78e36297dd4df3cce5be91bd6fba21977ab01108`. Tag nie jest niezmiennym digestem. `engine_reported_repo_digests` i `image_id` to lokalny odczyt Dockera, nie potwierdzenie autoryzowanego wdrożenia. `verified_remote_oci_digest` oraz `verified_production_source_sha` są `null`, dopóki osobna kontrola ich nie zweryfikuje. `verified_production_e2e` pozostaje false, bez testów dodatnich i ujemnych.


Nie usuwaj obrazów oznaczonych w katalogu jako działające — dopiero rzeczywisty roll-out i test rollbacku mogą pozwolić na ich bezpieczne wycofanie.

**Image-only GitHub Ops canaries:** the 38-resource fleet registry also includes two `github-ops-mcp` canaries. They are excluded from this 19-resource *production MCP/gateway* image catalog; their source is `mcp/github-mcp`, but each consumes an already-built OCI artifact, so do not mistake the Coolify `dockerimage` record for a Git source build.
