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
import logging


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_ALLOWED_SCOPES = {"tools:call"}
# Production defaults to the existing authenticated Paperclip native MCP gateway.
# Additional endpoints require an explicit operator-owned runtime env setting.
_DEFAULT_MCP_URLS = "https://paperclip-mcp.zariszlif.pl/mcp"


# Paperclip Core issues short-lived heartbeat_run gateway tokens for this exact
# public origin. The gateway ID is a server-minted opaque hex identifier, never
# a caller-chosen URL. No wildcard hostname, arbitrary path, query or redirect.
_PAPERCLIP_CORE_HOST = "paperclip.kompaszbiorek.pl"
_NATIVE_GATEWAY_PATH = re.compile(r"^/mcp/gateways/gw_[0-9a-f]{32}$")
_NATIVE_CORE_MCP_PATHS = frozenset({"/api/mcp/project-tools", "/mcp/runtime-tools"})


def _allowed_mcp_url(url: object) -> bool:
    if not isinstance(url, str) or any(ord(ch) < 33 or ord(ch) > 126 for ch in url):
        return False
    # An explicit empty allowlist is the operator's kill switch for ALL
    # per-run remote MCP destinations, including Core's first-party endpoints.
    allowlist = os.environ.get("HERMES_PAPERCLIP_MCP_URLS", _DEFAULT_MCP_URLS)
    if not allowlist.strip():
        return False
    allowed_exact = {item.strip() for item in allowlist.split(",") if item.strip()}
    try:
        parts = urlsplit(url)
        if not (
            parts.scheme == "https"
            and parts.hostname is not None
            and parts.username is None
            and parts.password is None
            and parts.port in (None, 443)
            and parts.query == ""
            and parts.fragment == ""
            and parts.hostname not in {"localhost", "127.0.0.1", "::1"}
            and "." in parts.hostname
        ):
            return False
        if url in allowed_exact:
            # Preserve the existing exact opt-in for public /mcp endpoints.
            return parts.path == "/mcp"
        return (
            parts.netloc == _PAPERCLIP_CORE_HOST
            and (
                _NATIVE_GATEWAY_PATH.fullmatch(parts.path) is not None
                or parts.path in _NATIVE_CORE_MCP_PATHS
            )
        )
    except ValueError:
        return False



class InvalidRunGrant(ValueError):
    """An invalid or unsafe run-scoped MCP request; message contains no input data."""


# Operational telemetry uses only fixed, source-controlled codes. Never log
# envelope fields, URLs, role/run identifiers, bearer contents or headers.
def _reject(reason: str) -> None:
    logging.getLogger("gateway.run_mcp").warning("run_mcp_denied reason=%s", reason)
    raise InvalidRunGrant


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
            _reject("envelope_shape")
        if envelope["version"] != 1 or envelope["run_id"] != run_id:
            _reject("version_or_run")
        for key in ("company_id", "agent_id", "issue_id", "run_id"):
            if not isinstance(envelope[key], str) or not _ID.fullmatch(envelope[key]):
                _reject("identity_fields")
        if envelope["profile"] != authenticated_profile:
            _reject("profile_mismatch")
        scopes = envelope["scopes"]
        if not isinstance(scopes, list) or not scopes or not set(scopes) <= _ALLOWED_SCOPES:
            _reject("scopes")
        expiry = datetime.fromisoformat(envelope["expires_at"].replace("Z", "+00:00"))
        if expiry.tzinfo is None or expiry <= (now or datetime.now(timezone.utc)):
            _reject("expiry")
        servers = envelope["servers"]
        if not isinstance(servers, list) or not 1 <= len(servers) <= 16:
            _reject("server_count")
        specs = []
        names = set()
        for server in servers:
            if not isinstance(server, dict) or set(server) != {"name", "url", "token"}:
                _reject("server_fields")
            name, url, token = server["name"], server["url"], server["token"]
            if not isinstance(name, str) or not _ID.fullmatch(name) or name in names:
                _reject("server_name")
            if not _allowed_mcp_url(url):
                _reject("server_url")
            if (not isinstance(token, str) or not token or len(token) > 8192
                    or any(not ch.isascii() or not ch.isprintable() or ch.isspace() for ch in token)):
                _reject("server_token")
            names.add(name)
            specs.append({"type": "http", "name": name, "url": url,
                          # Fail closed on cross-origin redirects and unsupported SSE fallback.
                          "strict_redirect_headers": True,
                          "headers": [{"name": "Authorization", "value": f"Bearer {token}"}]})
        # Scope keys are unique per run and profile; tool names and connections cannot cross runs.
        return specs, f"paperclip-run:{authenticated_profile}:{run_id}"
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        # A parsing/type error is reported with a fixed code only. Expected
        # _reject() paths already emitted their fixed category; do not log
        # exception text, because it could include untrusted input.
        if not isinstance(exc, InvalidRunGrant):
            logging.getLogger("gateway.run_mcp").warning("run_mcp_denied reason=parse_error")
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
