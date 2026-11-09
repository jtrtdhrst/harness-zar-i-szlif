# multica

Coolify project/service metadata for the Multica platform. Upstream source is
not vendored here, matching the `paperclip/` and `qdrant/` platform folders.

- Coolify project: `multica` (`fshlztqh95e17lcqvefcy1ye`)
- Service: `multica-stack` (`6ihjnudsifbcvklz5hqxdldc`)
- Public URL: `https://multica.zariszlif.pl`
- Upstream commit: `b1ea927def6490c43bedff537b6f4ed9a47fa828`
- Images: `ghcr.io/multica-ai/multica-backend:v0.8.1`,
  `ghcr.io/multica-ai/multica-web:v0.8.1`, `pgvector/pgvector:pg17`,
  `axllent/mailpit:v1.27.2`
- Data: `backend-uploads` and `pgdata` volumes owned by this Coolify project.
- Secrets and the full runtime environment remain in Coolify; nothing is
  committed here.

The platform is deployed from pinned upstream images, not built from this
repository. The only Git-built service in this repository that targets Multica
is `multica-mcp/`. Do not add a second Multica database or change the existing
`multica-stack` service when rebuilding the MCP adapter.
