# Self-hosted Plasmic — source snapshot status

This folder contains the self-host service's top-level files imported from `miloszspyrka-code/zar-i-szlif` at source commit `e3dd9cbb419a39aa6934546a1aa9a310058d6573`, including Compose, Docker setup, and the locally modified WAB file.

**Important: partial source migration, not yet buildable.** The source repository also contains 7,750 files (approximately 221 MB) in its vendored `plasmic/` workspace. Only the top-level files and selected service-specific files have been transferred; the vendored code under `platform/`, `packages/`, `plasmicpkgs/` and similar directories is NOT yet fully present here. Do not switch Coolify build source to this folder before complete synchronization and E2E validation.

The original `plasmic/SELFHOST.md` identifies `https://github.com/plasmicapp/plasmic` commit `85b861115687fde8e7970a9f270660aecb62b38e` as upstream for `platform/` and describes one local change in `platform/wab/src/wab/shared/devflags.ts`. Preserve upstream licensing and verify the full vendored diff before concluding that the source is reproducible. No deployment routes or data volumes were changed during this code copy.
