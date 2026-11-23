#!/usr/bin/env python3
"""Apply reviewed, repo-owned Python module overrides to the pinned RepoWise wheel."""
from importlib.util import find_spec
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent / "overrides"
spec = find_spec("repowise")
if spec is None or not spec.submodule_search_locations:
    raise SystemExit("RepoWise package not installed")
package = Path(next(iter(spec.submodule_search_locations))).resolve()
changes = []
for source in sorted(root.rglob("*")):
    if not source.is_file() or source.name == "README.md":
        continue
    if source.is_symlink():
        raise SystemExit(f"Override symlink forbidden: {source.relative_to(root)}")
    if source.suffix != ".py":
        raise SystemExit(f"Only .py overrides are allowed: {source.relative_to(root)}")
    rel = source.relative_to(root)
    dest = package / rel
    if not dest.is_file() or not dest.resolve().is_relative_to(package):
        raise SystemExit(f"Target must be an existing RepoWise Python module: {rel}")
    shutil.copyfile(source, dest)
    changes.append(str(rel))
print(f"RepoWise overrides applied: {len(changes)}", changes)
