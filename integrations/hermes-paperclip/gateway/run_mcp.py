"""Fail-closed validation for the Paperclip -> Hermes per-run MCP envelope.

The bearer remains private process memory and is passed only to Hermes' existing
session-local MCP facility. The MCP server remains the authority for token validity.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit
import os
import re


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_ALLOWED_SCOPES = {"tools:call"}
# Production defaults to the existing authenticated Paperclip native MCP gateway.
# Additional endpoints require an explicit operator-owned runtime env setting.
_DEFAULT_MCP_URLS = "https://paperclip-mcp.zariszlif.pl/mcp"


def _allowed_mcp_url(url: object) -> bool:
    if not isinstance(url, str) or any(ord(ch) < 33 or ord(ch) > 126 for ch in url):
        return False
    allowed = {
        value.strip() for value in os.environ.get(
            "HERMES_PAPERCLIP_MCP_URLS", _DEFAULT_MCP_URLS
        ).split(",") if value.strip()
    }
    if url not in allowed:
        return False
    try:
        parts = urlsplit(url)
        return (
            parts.scheme == "https"
            and parts.hostname is not None
            and parts.username is None
            and parts.password is None
            and parts.port in (None, 443)
            and parts.query == ""
            and parts.fragment == ""
            and parts.path == "/mcp"
            and parts.hostname not in {"localhost", "127.0.0.1", "::1"}
            and "." in parts.hostname
        )
    except ValueError:
        return False




class InvalidRunGrant(ValueError):
    """An invalid or unsafe run-scoped MCP request; message contains no input data."""


def validate_grant(envelope: object, *, authenticated_profile: str, run_id: str,
                   now: datetime | None = None) -> tuple[list[dict], str]:
    """Validate bounded identity metadata and produce private stdio/http MCP specs.

    The envelope's bearer is never logged or persisted. It is not trusted as claims:
    the receiving MCP gateway validates it on each tools/call.
    """
    try:
        if not isinstance(envelope, dict) or set(envelope) != {
            "version", "company_id", "agent_id", "issue_id", "run_id", "profile",
            "scopes", "expires_at", "servers",
        }:
            raise InvalidRunGrant
        if envelope["version"] != 1 or envelope["run_id"] != run_id:
            raise InvalidRunGrant
        for key in ("company_id", "agent_id", "issue_id", "run_id"):
            if not isinstance(envelope[key], str) or not _ID.fullmatch(envelope[key]):
                raise InvalidRunGrant
        if envelope["profile"] != authenticated_profile:
            raise InvalidRunGrant
        scopes = envelope["scopes"]
        if not isinstance(scopes, list) or not scopes or not set(scopes) <= _ALLOWED_SCOPES:
            raise InvalidRunGrant
        expiry = datetime.fromisoformat(envelope["expires_at"].replace("Z", "+00:00"))
        if expiry.tzinfo is None or expiry <= (now or datetime.now(timezone.utc)):
            raise InvalidRunGrant
        servers = envelope["servers"]
        if not isinstance(servers, list) or not 1 <= len(servers) <= 16:
            raise InvalidRunGrant
        specs = []
        names = set()
        for server in servers:
            if not isinstance(server, dict) or set(server) != {"name", "url", "token"}:
                raise InvalidRunGrant
            name, url, token = server["name"], server["url"], server["token"]
            if (not isinstance(name, str) or not _ID.fullmatch(name) or name in names
                    or not _allowed_mcp_url(url)
                    or not isinstance(token, str) or not token or len(token) > 8192
                    or any(not ch.isascii() or not ch.isprintable() or ch.isspace() for ch in token)):
                raise InvalidRunGrant
            names.add(name)
            specs.append({"type": "http", "name": name, "url": url,
                          # Fail closed on cross-origin redirects and unsupported SSE fallback.
                          "strict_redirect_headers": True,
                          "headers": [{"name": "Authorization", "value": f"Bearer {token}"}]})
        # Scope keys are unique per run and profile; tool names and connections cannot cross runs.
        return specs, f"paperclip-run:{authenticated_profile}:{run_id}"
    except (KeyError, TypeError, ValueError, AttributeError):
        raise InvalidRunGrant("invalid run MCP grant") from None


@contextmanager
def borrowed_run_tools(authority, envelope, *, authenticated_profile: str, run_id: str,
                       cwd: str = "."):
    """Borrow ephemeral MCP connections in Hermes' native scoped registry."""
    from gateway.session_local_mcp import _borrowed, _server_names

    servers, scope = validate_grant(envelope, authenticated_profile=authenticated_profile,
                                    run_id=run_id)
    names = _server_names(scope, servers)
    try:
        with _borrowed(authority, scope, servers, names, cwd, partial=False) as discovered:
            if len(discovered[1]) != len(servers):
                raise InvalidRunGrant("run MCP connection unavailable")
            yield scope
    finally:
        # _borrowed disconnects the last borrower; clear local references too.
        borrowed = getattr(authority, "_local_editor_mcp", None)
        if isinstance(borrowed, dict):
            borrowed.pop(scope, None)
