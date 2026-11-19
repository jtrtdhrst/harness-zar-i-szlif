# plasmic-production

Self-hosted Plasmic (Studio + WAB + codegen) deployed from this repository.
Everything the deployment needs is in this repo; the build is generated from
[`plasmicapp/plasmic`](https://github.com/plasmicapp/plasmic) pinned at
`e2e0b744f22638782736fe3a24ce9772e7cdb1b0` (2026-11-15) with local overrides.

## What runs

| Service | Image | Port | Purpose |
|---|---|---|---|
| `plasmic-db` | `postgres:15` | 5432 | WAB database |
| `plasmic-wab` | built from `platform/wab/Dockerfile` | 3004 | API + auth + publish |
| `plasmic-codegen` | same image, `codegen-backend.ts` | 3005 | `/api/v1/code/*`, `/api/v1/loader/*` |
| `plasmic-studio` | `studio.Dockerfile` (nginx) | 8080 | Studio UI + reverse proxy |

The only functional source change against upstream is `githubClientId` /
`githubAppName` in `platform/wab/src/wab/shared/devflags.ts` (our GitHub App).
The GitHub App private key is **not** in the image: `plasmic-wab` writes it from
`PLASMIC_GITHUB_SECRETS_B64` at container start.

Images are built on the VPS and referenced by exact tag
(`plasmic-wab:2026-11-15-e2e0b744`, `plasmic-studio:2026-11-15-e2e0b744`);
Coolify only pulls those local tags. Keep the previous tag until the new one has
passed health, public readback and the rollback check. WAB runs pending TypeORM
migrations at startup (`maybeMigrateDatabase`), so the database schema moves
forward with the first boot of a new image.

## Local run

```bash
cp .env.example .env   # fill in every value
docker compose up -d --build
curl -s http://127.0.0.1:8080/api/v1/app-config
```

First build takes ~30–60 minutes (pnpm install + `make` + rsbuild Studio bundle).

## Coolify

- Resource type: Application, Git repository `miloszspyrka-code/plasmic-production`.
- Build pack: Docker Compose, base directory `/`, compose `docker-compose.yml`.
- Domain: `plasmic-studio` service on port 8080.
- Environment: every key from `.env.example`.
- Persistent volume: `plasmic_pgdata` (database).
- Resource sizing: first build needs ~4 GB RAM and ~8 GB free disk for build cache.

## Data migration from the old instance

```bash
# old host, user docker
docker exec plasmic-plasmic-db-1 pg_dump -U wab -d wab --no-owner --no-privileges > wab.sql
# new instance (container name from `docker ps`)
docker exec -i <new-db-container> psql -U wab -d wab < wab.sql
```

## License

`platform/` is AGPL-3.0 (`LICENSE.platform.md`); everything outside `platform/`
is MIT (`LICENSE.md`). Running this as a public network service means offering
the corresponding source (including local modifications) to its users.

## Upgrade and rollback

For the upstream `e2e0b744` transition, follow [`UPGRADE-20261115.md`](UPGRADE-20261115.md) before any live cutover. The runbook covers `ADMIN_EMAILS` JSON parsing, PostgreSQL 15 backup and migration risk, isolated canary checks, image provenance and rollback. This branch does **not** authorize or perform a production deployment.
