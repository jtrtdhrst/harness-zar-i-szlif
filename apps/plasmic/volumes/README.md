# Volumes — plasmic

This directory marks the project-owned data location. Runtime data belongs to
the same Coolify project/service as the application; it must not be mounted
from another project.

Committed files: only `.gitkeep` and this README. Never commit database dumps,
model files, browser profiles, credentials or other runtime data.

The authoritative Coolify volume names and backup/restore notes are in
`docs/COOLIFY-PROJECTS.md` and the service README.
