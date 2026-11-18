# Ubuntu operations MCP (`ubuntu-mcp-bridge`)

Authenticated Streamable HTTP MCP in front of
[`mcp-ssh-manager`](https://github.com/bvisible/mcp-ssh-manager) (stdio) → SSH → the
managed Ubuntu host.

```
client ──Bearer──▶ POST /mcp (bridge, :8765) ──stdio──▶ mcp-ssh-manager ──SSH──▶ host
                     └─ audit JSONL (redacted)
```

- `server.mjs` — the bridge (stateless HTTP, one serialized stdio child, redaction +
  JSONL audit, `GET /healthz`, OAuth 2.1 discovery for ChatGPT).
- `Dockerfile` — Node 24 image that installs `mcp-ssh-manager@3.8.6` from npm and
  verifies the pinned version at build time.
- `bootstrap-harness-ops.sh` — run ON THE HOST: creates the `harness-ops` user,
  authorizes the SSH key, grants NOPASSWD sudo (idempotent).

## Build

```bash
docker build -t ubuntu-mcp-bridge:local .
```

## Run

```bash
docker run --rm -p 8765:8765 \
  --env-file .env \
  -v "$PWD/secrets/bridge-bearer-token:/bridge-config/bridge-bearer-token:ro" \
  -v "$PWD/secrets/url-key:/bridge-config/url-key:ro" \
  -v "$PWD/secrets/harness-ops:/bridge-config/harness-ops:ro" \
  -v "$PWD/secrets/known_hosts:/bridge-config/known_hosts:ro" \
  -v "$PWD/audit:/audit" \
  ubuntu-mcp-bridge:local
```

Secrets are files, not env vars: `bridge-bearer-token` (Bearer for `/mcp`),
`url-key` (optional, `POST /mcp?key=<url-key>` for clients without headers),
`harness-ops` (SSH private key), `known_hosts` (SSH host keys). `test-auth.mjs`
(`node test-auth.mjs`) checks the auth boundary and the OAuth flow with a stub
stdio child.

## OAuth for ChatGPT custom MCP

ChatGPT custom connectors support OAuth, not a static key in the URL. The bridge
implements the MCP authorization minimum:

- `GET /.well-known/oauth-protected-resource[/mcp]` → protected resource metadata.
- `GET /.well-known/oauth-authorization-server[/mcp]` → authorization server metadata
  (PKCE `S256`, `token_endpoint_auth_methods_supported: ["none"]`).
- `GET|POST /authorize` → HTML form where a human enters the URL key once; only
  `https://chatgpt.com/...` redirect URIs are accepted.
- `POST /token` → single-use code + PKCE verifier exchange, HMAC-signed access token
  (1 h, no refresh: an expired token re-triggers the flow).

`BRIDGE_PUBLIC_URL` must be the public HTTPS origin, otherwise discovery documents
contain relative URLs. Cloudflare Access must bypass `/.well-known/*` and `/token`
(ChatGPT fetches them server-side); `/authorize` stays behind Access so the human
gate remains.

Behind OpenAI Secure MCP Tunnel set `BRIDGE_TRUST_TUNNEL=1`: the tunnel URL has no
key, so the tunnel itself is the trust boundary and no OAuth challenge is emitted.

## Coolify

Build directory `/mcp/ubuntu`, Dockerfile `Dockerfile`, port `8765`. Mount the three
secret files and an audit volume.

## Provenance

Source of the running container `local/ubuntu-mcp-bridge:3.8.6` on the production
host. The MCP implementation itself is the upstream npm package
`mcp-ssh-manager@3.8.6` (`bvisible/mcp-ssh-manager`, MIT), installed by the
Dockerfile.
