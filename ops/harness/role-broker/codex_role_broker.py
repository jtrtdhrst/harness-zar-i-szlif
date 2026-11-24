#!/usr/bin/env python3
"""Role-authenticated, constrained Responses API relay for Hermes OAuth Codex.

Trusted service holds the upstream OAuth account. Landlocked agent tasks only
receive a role-specific bearer, never auth.json, refresh tokens or shared .env.
This is a staging candidate: activation requires a separate reviewed release.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import stat
from pathlib import Path
from typing import Callable

from aiohttp import ClientSession, ClientTimeout, ClientPayloadError, ClientConnectionError, web

UPSTREAM = "https://chatgpt.com/backend-api/codex"
ROLES = frozenset(("ceo", "cho", "cmo", "coo", "cpo", "cto", "designer",
                   "email-creative", "engineer", "harness-engineer",
                   "lifecycle-ops", "mascot-designer", "mcp-engineer", "ui-qa"))
MODEL_ALLOWLIST = frozenset(("gpt-6-luna",))
MODEL_ALIASES = frozenset(("gpt-6-luna", "openai-codex/gpt-6-luna"))

def canonical_model(value: object) -> str | None:
    """Accept only the pinned Luna model and its Multica Codex-qualified ID."""
    return "gpt-6-luna" if isinstance(value, str) and value in MODEL_ALIASES else None
MAX_BODY = 1_048_576
KEY_ROOT = Path("/srv/multica-zar/.config/hermes")


def role_secret(role: str, root: Path = KEY_ROOT) -> str:
    """Open root -> role -> key with pinned no-follow FDs and checked identity.

    Every directory and the key must belong to the trusted service UID and be
    private. Never stat the pathname then reopen it: path swaps must not change
    the bytes read by an already-validated file descriptor.
    """
    if role not in ROLES:
        raise ValueError("role_not_allowed")
    owner = os.geteuid()
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    key_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC

    def checked_directory(fd: int, code: str) -> None:
        metadata = os.fstat(fd)
        if (not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != owner or (metadata.st_mode & 0o077)):
            raise ValueError(code)

    try:
        root_fd = os.open(root, dir_flags)
    except OSError as exc:
        raise ValueError("role_key_root_unavailable") from exc
    try:
        checked_directory(root_fd, "role_key_root_untrusted")
        try:
            role_fd = os.open(role, dir_flags, dir_fd=root_fd)
        except OSError as exc:
            raise ValueError("role_key_role_directory_invalid") from exc
        try:
            checked_directory(role_fd, "role_key_role_directory_untrusted")
            try:
                key_fd = os.open("api-key", key_flags, dir_fd=role_fd)
            except OSError as exc:
                raise ValueError("role_key_path_invalid") from exc
            try:
                metadata = os.fstat(key_fd)
                if (not stat.S_ISREG(metadata.st_mode)
                        or metadata.st_uid != owner or (metadata.st_mode & 0o077)):
                    raise ValueError("role_key_permissions_invalid")
                # Read from the same already validated inode; no second path lookup.
                with os.fdopen(key_fd, "r", encoding="utf-8", closefd=False) as handle:
                    key = handle.read(4096).strip()
            finally:
                os.close(key_fd)
        finally:
            os.close(role_fd)
    finally:
        os.close(root_fd)
    if len(key) < 40 or len(key) > 4096:
        raise ValueError("role_key_length_invalid")
    return key


def native_credential() -> tuple[str, str, dict[str, str]]:
    """Resolve+refresh OAuth solely inside the trusted service, never a task."""
    from hermes_cli.auth_codex import resolve_codex_runtime_credentials
    from agent.codex_headers import codex_cloudflare_headers

    credential = resolve_codex_runtime_credentials()
    base = str(credential.get("base_url") or "").rstrip("/")
    if base != UPSTREAM:
        raise RuntimeError("upstream_not_pinned")
    key = str(credential.get("api_key") or "").strip()
    if not key:
        raise RuntimeError("upstream_credential_missing")
    return base, key, codex_cloudflare_headers(key, base_url=base)


class RoleCapacity:
    """In-process role budget. Never counts denied credentials against a role.

    The service must bind to loopback and run as a single process; capacity
    state is deliberately local and restart reset (not a billing ledger).
    """

    def __init__(self, *, quota: int = 8, window_seconds: float = 60.0,
                 max_total: int = 3):
        from collections import deque
        self.quota = quota
        self.window_seconds = window_seconds
        self.max_total = max_total
        self._calls = {role: deque() for role in ROLES}
        self._active = {role: 0 for role in ROLES}
        self._total = 0
        self._lock = asyncio.Lock()

    async def admit(self, role: str) -> tuple[bool, str]:
        import time
        now = time.monotonic()
        async with self._lock:
            history = self._calls[role]
            while history and now - history[0] >= self.window_seconds:
                history.popleft()
            if self._active[role] >= 1 or self._total >= self.max_total:
                return False, "capacity_exceeded"
            if len(history) >= self.quota:
                return False, "rate_exceeded"
            history.append(now)
            self._active[role] += 1
            self._total += 1
            return True, "ok"

    async def release(self, role: str) -> None:
        async with self._lock:
            if self._active[role] <= 0 or self._total <= 0:
                raise RuntimeError("capacity_release_unbalanced")
            self._active[role] -= 1
            self._total -= 1


def error(code: int, message: str) -> web.Response:
    return web.json_response({"error": {"code": message}}, status=code)


@web.middleware
async def trusted_role(request: web.Request, handler):
    if request.path == "/healthz":
        return await handler(request)
    role = request.match_info.get("role", "")
    if role not in ROLES:
        return error(404, "route_not_allowed")
    header = request.headers.get("Authorization", "")
    presented = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
    try:
        expected = request.app["key_resolver"](role)
    except (ValueError, OSError):
        return error(503, "role_identity_unavailable")
    if not presented or not hmac.compare_digest(presented, expected):
        return error(401, "role_not_authorized")
    # Quota is acquired after data-plane payload validation in responses(),
    # so authenticated but invalid requests cannot starve a legitimate role.
    return await handler(request)


async def models(request: web.Request):
    return web.json_response({"object": "list", "data": [
        {"id": v, "object": "model", "owned_by": "role-broker"}
        for v in sorted(MODEL_ALLOWLIST)
    ]})


async def responses(request: web.Request):
    if request.content_length is not None and request.content_length > MAX_BODY:
        return error(413, "request_too_large")
    if request.content_type != "application/json":
        return error(415, "json_required")
    try:
        body = await request.read()
        if len(body) > MAX_BODY:
            return error(413, "request_too_large")
        document = json.loads(body)
    except (ValueError, UnicodeDecodeError, web.HTTPException):
        return error(400, "invalid_json")
    if not isinstance(document, dict):
        return error(403, "model_not_allowed")
    model = canonical_model(document.get("model"))
    if model is None:
        return error(403, "model_not_allowed")
    # Hermes/Multica may retain the provider-qualified ID; Codex upstream expects
    # the native model identifier. Rewrite only the exact pinned alias.
    if document["model"] != model:
        document["model"] = model
        body = json.dumps(document, separators=(",", ":")).encode("utf-8")
    if document.get("stream") is not True or document.get("store") is not False:
        return error(400, "codex_requires_stream_true_store_false")
    if "input" not in document:
        return error(400, "input_required")
    role = request.match_info["role"]
    admitted, reason = await request.app["capacity"].admit(role)
    if not admitted:
        return error(429, reason)
    try:
        try:
            base, token, official_headers = await asyncio.to_thread(request.app["credential_resolver"])
        except Exception:
            # No OAuth details, provider errors, account IDs or tokens leak to clients.
            return error(503, "upstream_auth_unavailable")
        if base != UPSTREAM:
            return error(503, "upstream_not_pinned")
        headers = {"Authorization": "Bearer " + token, "Accept": "text/event-stream",
                   "Content-Type": "application/json", **official_headers}
        client: Callable = request.app["http_factory"]
        try:
            async with client(timeout=ClientTimeout(total=None, sock_connect=10, sock_read=180)) as session:
                async with session.post(base + "/responses", data=body, headers=headers,
                                        allow_redirects=False) as upstream:
                    if upstream.status != 200:
                        # Never relay upstream error bodies: they may include auth metadata.
                        return error(502, "upstream_http_failure")
                    output = web.StreamResponse(status=200, headers={
                        "Content-Type": "text/event-stream", "Cache-Control": "no-store",
                        "X-Accel-Buffering": "no"})
                    await output.prepare(request)
                    try:
                        async for chunk in upstream.content.iter_chunked(16384):
                            await output.write(chunk)
                        await output.write_eof()
                    except (ClientPayloadError, ClientConnectionError,
                            asyncio.TimeoutError, OSError):
                        # HTTP headers were already sent; cannot relabel a 200
                        # as 502. Send an explicit terminal SSE failure instead
                        # of a traceback, truncated silent success or false DONE.
                        try:
                            await output.write(
                                b'event: error\ndata: {"error":{"code":"upstream_stream_interrupted"}}\n\n')
                            await output.write_eof()
                        except (ConnectionResetError, OSError):
                            # Client disconnected; never log or relay OAuth details.
                            pass
                    return output
        except (asyncio.TimeoutError, OSError):
            return error(502, "upstream_transport_failure")

    finally:
        await request.app["capacity"].release(role)

def create_app(*, key_resolver=role_secret, credential_resolver=native_credential,
               http_factory=ClientSession):
    app = web.Application(middlewares=[trusted_role], client_max_size=MAX_BODY)
    app["key_resolver"] = key_resolver
    app["credential_resolver"] = credential_resolver
    app["http_factory"] = http_factory
    app["capacity"] = RoleCapacity()
    async def health(_):
        return web.json_response({"ok": True})
    app.router.add_get("/healthz", health)
    app.router.add_get("/p/{role}/v1/models", models)
    app.router.add_post("/p/{role}/v1/responses", responses)
    return app


def main():
    # Fail closed before opening global OAuth or starting an HTTP listener.
    # This is a broker process, never a root-executed agent or release hook.
    if os.geteuid() == 0:
        raise RuntimeError("broker_must_be_unprivileged")
    if os.environ.get("HERMES_HOME") != "/srv/multica-zar/.hermes":
        raise RuntimeError("trusted_hermes_home_required")
    host = os.getenv("ROLE_BROKER_HOST", "127.0.0.1")
    if host != "127.0.0.1":
        raise RuntimeError("loopback_only")
    port = int(os.getenv("ROLE_BROKER_PORT", "7468"))
    if port < 1024 or port > 65535:
        raise RuntimeError("invalid_port")
    web.run_app(create_app(), host=host, port=port, access_log=None)


if __name__ == "__main__":
    main()
