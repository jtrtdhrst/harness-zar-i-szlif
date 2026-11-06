# opik-mcp

Coolify project/service folder. Runtime data volumes are owned by this
project; only `volumes/` markers are committed.

- Project metadata: `project.yml`
- Runtime source/image: see `docs/COOLIFY-PROJECTS.md`
- No secrets or runtime data in Git.

## Cloudflare Access + origin JWT (production 2026-11-05)

The deployment is **Cloudflare Access Managed OAuth → Cloudflare Tunnel → Coolify Caddy → private Nginx proxy → Opik MCP**. The Caddy upstream is `proxy-egasedqaofxnzcqppuxi805h:8080` on the `coolify` network, not the host-published port. The host publishes port 18082 on `127.0.0.1` only. Coolify service UUID: `egasedqaofxnzcqppuxi805h`.

An Access application on `mcp-opik.kompaszbiorek.pl` is enabled with dynamic OAuth registration limited to ChatGPT callback URLs and a pre-approved human identity policy (NOT bypass everyone). Access issues opaque OAuth tokens to the client and injects a signed JWT at the origin as `Cf-Access-Jwt-Assertion`. Nginx `auth_request` calls `access-guard` to check that JWT against the Cloudflare JWKS, issuer and exact application audience. The origin does **not** rely only on Cloudflare edge routing. The guard is non-root and fail-closed; absent/expired/wrongly signed/wrong issuer/wrong audience tokens are denied. Nginx strips JWT, Access user-email and Cookie headers before forwarding to Opik. The existing dummy backend bearer remains internal only.

Versioned source: `access-guard/guard.py`, `access-guard/Dockerfile`, `access-guard/test_guard.py`, `proxy/mcp-proxy.conf`. Actual production guard image digest at deployment: `sha256:475ab2e3ed35966dcc86a55920f79edf65cf3c7f2882522ce3cf82cf15d71fd6`. **This is an image built locally and referenced from Coolify, not proof of Git-backed automatic deployment.** Production Nginx source was mounted from `/home/opencode/projects/opik/mcp-proxy.conf`. Its reviewed SHA256 after header scrubbing: `2292a15220f1dcc72b89f2f10cac73b151a9ae658b08ba027896d22a6e23e323`. Do not print credentials from runtime Compose.

Run regressions with:
```bash
python -m pip install PyJWT==2.10.1 cryptography==46.0.5
python -m unittest discover -s opik-mcp/access-guard -p test_guard.py -v
docker build -t local/opik-access-guard:test opik-mcp/access-guard
```

### Production verification

- Unauthenticated public HTTPS MCP: 401 with a Bearer/OAuth challenge.
- Unauthenticated local Nginx proxy, direct Caddy route, forged JWT: 403.
- Docker `access-guard` and Nginx proxy: running/healthy; nginx config validation and reload PASS.
- `opik-run-enricher` still reads Opik through its internal API and reads Hindsight bank stats, without external MCP OAuth.
- Known genuine Paperclip issue run `20269f6a-ec02-426c-9921-c9afac2f8adb` resolves to an Opik trace with LLM/tool spans, `paperclip.run.audit_summary` and `hindsight.bank.stats_snapshot`. The latter is a bank diagnostic, **not proof of native Hindsight use in that run**.
- **Outstanding mandatory positive gate:** reconnect the existing ChatGPT Opik plugin via the Access OAuth flow, then verify authorized MCP `tools/list` and `tools/call`. A failed tool after Access hardening is not a reason to reopen anonymous access.
- Stock Opik MCP queries indexed Opik content; it is not a direct authorized PC/VAI/Ubuntu/Coolify administrative client. Future data enrichment must use least-privilege named adapters and sanitization. Do not claim full cross-system E2E without those readbacks.

### Rollback and change control

Preserve root-only backup of the live Nginx config; validate candidate with `nginx -t` and reload, restoring backup on failure. Roll back deployment only to an already verified image by digest. **Never** roll back to public bypass authentication to fix OAuth reconnect. Release/promote through the per-service approved lane with independent reviewer; merging this source alone must not be treated as deployment.
