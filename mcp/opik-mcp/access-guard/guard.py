#!/usr/bin/env python3
"""Fail-closed Cloudflare Access assertion verifier for the private Opik MCP origin."""
import os
import sys
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jwt
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError

MAX_ASSERTION_LENGTH = 16_384


def verify_assertion(value, key_provider, issuer, audience, allowed_service_client_id=""):
    if not isinstance(value, str) or not 32 <= len(value) <= MAX_ASSERTION_LENGTH:
        return False
    if value.count(".") != 2:
        return False
    try:
        key = key_provider.get_signing_key_from_jwt(value).key
        claims = jwt.decode(
            value, key, algorithms=["RS256"], issuer=issuer, audience=audience,
            leeway=15, options={"require": ["exp", "iss", "aud", "sub", "iat"]},
        )
        # A signed Cloudflare service-token JWT is not a human identity.
        # Admit only one explicitly configured client ID; default is deny.
        if "service_token_id" in claims or "common_name" in claims:
            service_id = claims.get("service_token_id")
            common_name = claims.get("common_name")
            return bool(
                isinstance(allowed_service_client_id, str)
                and 8 <= len(allowed_service_client_id) <= 256
                and isinstance(service_id, str)
                and isinstance(common_name, str)
                and hmac.compare_digest(service_id, allowed_service_client_id)
                and hmac.compare_digest(common_name, allowed_service_client_id)
                and claims.get("sub") == ""
                and claims.get("email") in (None, "")
            )
        # Preserve the existing signed, interactive human identity path.
        return bool(isinstance(claims.get("email"), str) and "@" in claims["email"])
    except (InvalidTokenError, PyJWKClientError, ValueError, KeyError, TypeError):
        return False
    except Exception:
        # No tokens, claims or upstream responses are ever logged.
        return False


class GuardHandler(BaseHTTPRequestHandler):
    server_version = "OpikAccessGuard/1"
    sys_version = ""

    def log_message(self, _format, *_args):
        # Avoid logging assertion headers, paths or any user metadata.
        return

    def do_GET(self):
        if self.path == "/healthz":
            return self.reply(204)
        if self.path != "/verify":
            return self.reply(404)
        token = self.headers.get("Cf-Access-Jwt-Assertion", "")
        status = 204 if verify_assertion(
            token, self.server.jwk_client, self.server.issuer, self.server.audience,
            self.server.service_token_client_id,
        ) else 403
        return self.reply(status)

    def reply(self, code):
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()


def main():
    issuer = os.environ["CF_ACCESS_ISSUER"].rstrip("/")
    audience = os.environ["CF_ACCESS_AUD"]
    assert issuer.startswith("https://") and issuer.endswith(".cloudflareaccess.com")
    assert len(audience) >= 20
    jwks_url = issuer + "/cdn-cgi/access/certs"
    server = ThreadingHTTPServer(("0.0.0.0", 8088), GuardHandler)
    server.issuer = issuer
    server.audience = audience
    server.service_token_client_id = os.environ.get("CF_ACCESS_SERVICE_TOKEN_CLIENT_ID", "").strip()
    server.jwk_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300, timeout=4)
    print("opik_access_guard_ready", flush=True)
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
