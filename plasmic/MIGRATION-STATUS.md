# Plasmic self-host source — migration status

Upstream: `plasmicapp/plasmic` @ `e2e0b744f22638782736fe3a24ce9772e7cdb1b0` (2026-11-15).
Previous pin: `85b861115687fde8e7970a9f270660aecb62b38e` (2026-10-09), 212 commits back.

Upstream delta between the two pins: **207 added, 160 removed, 1,160 modified** blobs
(8,919 → 8,970 blobs, recursive GitHub Trees comparison, untruncated). This is a
source-level upgrade, not a patch bump: it must clear the canary build in
`plasmic/UPGRADE-20261115.md` before it can serve production.

Local overlay over the pinned upstream, copied by `plasmic/bootstrap-source.sh`:

- **added**: `.dockerignore`, `.env.example`, `SELFHOST.md`, `studio.Dockerfile`, `studio/nginx.conf`
- **modified**: `docker-compose.yml` (own service definitions, PostgreSQL 15 retained),
  `platform/wab/src/wab/shared/devflags.ts` (only `githubClientId` / `githubAppName`)
- **omitted**: 16 upstream paths deleted by the bootstrap script

The complete public upstream is a Git submodule at `plasmic/upstream/`.

From a clean clone of this repository, run:

```bash
bash plasmic/bootstrap-source.sh
```

This generates `.build/plasmic/`, matching the recorded full source snapshot while avoiding duplication of 221 MB of upstream source. **Do not directly point Coolify at `plasmic/`**: the live build needs a generated complete context, a validated release process, E2E and rollback. This change only migrates source definitions, not deployments or persistent databases. Preserve upstream AGPL-3.0 license obligations.
