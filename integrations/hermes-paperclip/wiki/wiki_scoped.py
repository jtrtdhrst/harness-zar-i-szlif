#!/usr/bin/env python3
"""Profile-scoped, read-only MCP interface to the synchronized Paperclip Wiki."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

PROFILES = frozenset((
    "ceo", "cho", "cmo", "coo", "cpo", "cto", "designer",
    "email-creative", "engineer", "harness-engineer",
    "lifecycle-ops", "mascot-designer", "mcp-engineer", "ui-qa",
))
ROOT = Path("/opt/data/wiki-paperclip-test").resolve()
MAX_BYTES = 512 * 1024
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False,
    idempotentHint=True, openWorldHint=False,
)
parser = argparse.ArgumentParser()
parser.add_argument("--profile", choices=sorted(PROFILES), required=True)
PROFILE = parser.parse_args().profile
ALLOWED = (
    ("wiki", "concepts"),
    ("wiki", "sources"),
    ("wiki", "agents", PROFILE),
    *((
        ("wiki", "agents", "harness"),
    ) if PROFILE in ("cho", "harness-engineer") else ()),
)
server = MCPServer(
    name="Paperclip Wiki — scoped read-only",
    instructions=(
        "Read-only Paperclip Wiki snapshot. Only shared concepts/sources "
        "and your own authorized role documentation are accessible."
    ),
)


def _allowed(path: str) -> bool:
    parts = Path(path).parts
    return any(parts[:len(prefix)] == prefix and len(parts) > len(prefix)
               for prefix in ALLOWED)


def _safe_page(path: str) -> Path:
    if not isinstance(path, str) or not path or len(path) > 300:
        raise ValueError("A relative Markdown path is required")
    candidate = Path(path)
    if (candidate.is_absolute() or ".." in candidate.parts
            or candidate.suffix.lower() != ".md" or not _allowed(path)):
        raise ValueError("Page not permitted for this profile")
    resolved = (ROOT / candidate).resolve()
    if (not resolved.is_relative_to(ROOT) or not resolved.is_file()
            or resolved.stat().st_size > MAX_BYTES):
        raise ValueError("Page missing or outside allowed root")
    current = ROOT
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symbolic links are not permitted")
    return resolved


def _pages():
    if not ROOT.is_dir():
        raise RuntimeError("Wiki snapshot unavailable")
    result = []
    for path in ROOT.rglob("*.md"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if not _allowed(rel):
            continue
        try:
            if _safe_page(rel) == path.resolve():
                result.append(path)
        except ValueError:
            continue
    return sorted(result)


@server.tool(
    description="List accessible Markdown pages in Paperclip Wiki.",
    annotations=READ_ONLY,
)
def wiki_list(prefix: str = "", limit: int = 100) -> dict:
    if (not isinstance(prefix, str) or len(prefix) > 200
            or Path(prefix).is_absolute() or ".." in Path(prefix).parts):
        raise ValueError("Invalid prefix")
    out = []
    for page in _pages():
        rel = page.relative_to(ROOT).as_posix()
        if rel.startswith(prefix):
            out.append({"path": rel, "bytes": page.stat().st_size})
        if len(out) >= max(1, min(int(limit), 200)):
            break
    return {"pages": out, "returned": len(out), "read_only": True, "profile": PROFILE}


@server.tool(
    description="Read one authorized Markdown page with content and SHA-256.",
    annotations=READ_ONLY,
)
def wiki_read(path: str) -> dict:
    page = _safe_page(path)
    raw = page.read_bytes()
    return {
        "path": page.relative_to(ROOT).as_posix(),
        "content": raw.decode("utf-8"),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "read_only": True,
    }


@server.tool(
    description="Search authorized Wiki pages and bounded excerpts.",
    annotations=READ_ONLY,
)
def wiki_search(query: str, limit: int = 15) -> dict:
    if not isinstance(query, str) or not query.strip() or len(query) > 120:
        raise ValueError("Query length out of range")
    needle = query.casefold().strip()
    out = []
    for page in _pages():
        rel = page.relative_to(ROOT).as_posix()
        content = page.read_text(encoding="utf-8")
        idx = content.casefold().find(needle)
        if idx < 0 and needle not in rel.casefold():
            continue
        out.append({
            "path": rel,
            "snippet": content[max(0, idx - 100):idx + 230]
            if idx >= 0 else content[:230],
        })
        if len(out) >= max(1, min(int(limit), 30)):
            break
    return {"matches": out, "returned": len(out), "read_only": True, "profile": PROFILE}


if __name__ == "__main__":
    server.run(transport="stdio")
