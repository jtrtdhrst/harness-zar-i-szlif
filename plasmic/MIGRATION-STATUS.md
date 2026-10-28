# Plasmic self-host source — migration status

Source: product `main` @ `e3dd9cbb419a39aa6934546a1aa9a310058d6573`. Upstream: `plasmicapp/plasmic` @ `85b861115687fde8e7970a9f270660aecb62b38e`.

A complete recursive Git SHA comparison found exactly **6 added, 2 modified, 16 omitted** files relative to this pinned upstream (7,750 source blobs vs 7,760 upstream blobs). The 8 local additions/overrides are stored in this directory, including Compose, WAB devflags and Studio configuration. The complete public upstream is a Git submodule at `plasmic/upstream/`.

From a clean clone of this repository, run:

```bash
bash plasmic/bootstrap-source.sh
```

This generates `.build/plasmic/`, matching the recorded full source snapshot while avoiding duplication of 221 MB of upstream source. **Do not directly point Coolify at `plasmic/`**: the live build needs a generated complete context, a validated release process, E2E and rollback. This change only migrates source definitions, not deployments or persistent databases. Preserve upstream AGPL-3.0 license obligations.
