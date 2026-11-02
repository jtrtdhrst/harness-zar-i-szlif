#!/usr/bin/env python3
"""Read-only MCP view of the canonical Paperclip Wiki Markdown mirror for Hermes Test."""
from __future__ import annotations
import hashlib
from pathlib import Path
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

ROOT = Path("/opt/data/wiki-paperclip-test").resolve()
MAX_BYTES = 512 * 1024
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
server = MCPServer(name="Hermes Test Wiki (read-only)", instructions="Read canonical Paperclip Wiki Markdown. No writes; no secrets; read-only synchronized snapshot.")

def _pages():
    if not ROOT.is_dir():
        raise RuntimeError("Wiki mirror unavailable")
    return sorted(p for p in ROOT.rglob("*.md") if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(ROOT))

def _safe_page(path: str) -> Path:
    if not isinstance(path, str) or not path or len(path) > 300:
        raise ValueError("A relative Markdown path is required")
    raw = Path(path)
    if raw.is_absolute() or ".." in raw.parts or raw.suffix.lower() != ".md":
        raise ValueError("Only Markdown paths within Wiki are accepted")
    resolved = (ROOT / raw).resolve()
    if not resolved.is_relative_to(ROOT) or not resolved.is_file() or resolved.is_symlink():
        raise ValueError("Wiki file not found or outside allowed root")
    if resolved.stat().st_size > MAX_BYTES:
        raise ValueError("Wiki page exceeds read limit")
    return resolved

@server.tool(description="List Markdown pages in the synchronized Paperclip Wiki. Read-only.", annotations=READ_ONLY)
def wiki_list(prefix: str = "", limit: int = 100) -> dict:
    """List relative Markdown paths and sizes; never read non-Markdown files."""
    if not isinstance(prefix, str) or len(prefix) > 200 or ".." in Path(prefix).parts or Path(prefix).is_absolute():
        raise ValueError("Invalid prefix")
    bounded = max(1, min(int(limit), 200))
    pages = []
    for page in _pages():
        rel = page.relative_to(ROOT).as_posix()
        if rel.startswith(prefix):
            pages.append({"path": rel, "bytes": page.stat().st_size})
            if len(pages) >= bounded:
                break
    return {"pages": pages, "returned": len(pages), "read_only": True}

@server.tool(description="Read one canonical Paperclip Wiki Markdown page with content and SHA-256 hash. Read-only.", annotations=READ_ONLY)
def wiki_read(path: str) -> dict:
    """Return page content after path confinement, size and extension checks."""
    page = _safe_page(path)
    raw = page.read_bytes()
    return {"path": page.relative_to(ROOT).as_posix(), "content": raw.decode("utf-8"), "sha256": hashlib.sha256(raw).hexdigest(), "read_only": True}

@server.tool(description="Search Markdown file names and content in Paperclip Wiki. Read-only.", annotations=READ_ONLY)
def wiki_search(query: str, limit: int = 15) -> dict:
    """Return bounded matched snippets, not whole documents."""
    if not isinstance(query, str) or not query.strip() or len(query) > 120:
        raise ValueError("Search query must be between 1 and 120 characters")
    needle = query.casefold().strip()
    matches = []
    for page in _pages():
        if page.stat().st_size > MAX_BYTES:
            continue
        rel = page.relative_to(ROOT).as_posix()
        text = page.read_text(encoding="utf-8")
        idx = text.casefold().find(needle)
        if idx < 0 and needle not in rel.casefold():
            continue
        snippet = text[max(0, idx - 100): idx + 230] if idx >= 0 else text[:230]
        matches.append({"path": rel, "snippet": snippet})
        if len(matches) >= max(1, min(int(limit), 30)):
            break
    return {"matches": matches, "returned": len(matches), "read_only": True}

if __name__ == "__main__":
    server.run(transport="stdio")
