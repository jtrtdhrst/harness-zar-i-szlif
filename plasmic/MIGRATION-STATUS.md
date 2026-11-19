# Plasmic self-host source — migration status

Upstream: `plasmicapp/plasmic` @ `e2e0b744f22638782736fe3a24ce9772e7cdb1b0` (2026-11-15, `master`).
Previous pin: `85b861115687fde8e7970a9f270660aecb62b38e` (2026-10-09). The live images
before 2026-11-15 were tagged `2026-11-05-8f017624`; that tag's provenance is not
recorded in this repository.

A complete recursive Git SHA comparison against the current pin finds exactly
**5 added, 2 modified, 16 omitted** files:
added `.dockerignore`, `.env.example`, `SELFHOST.md`, `studio.Dockerfile`,
`studio/nginx.conf`; modified `docker-compose.yml` and
`platform/wab/src/wab/shared/devflags.ts`; omitted the upstream files listed in
`bootstrap-source.sh` (CI/IDE artifacts not needed for the build). The complete
public upstream is a Git submodule at `plasmic/upstream/`.

From a clean clone of this repository, run:

```bash
bash plasmic/bootstrap-source.sh
```

This generates `.build/plasmic/`, matching the recorded build source while
avoiding duplication of the upstream tree. **Do not directly point Coolify at
`plasmic/`**: the live build needs a generated complete context, a validated
release process, E2E and rollback. Preserve upstream AGPL-3.0 license obligations.
