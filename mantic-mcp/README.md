# Mantic MCP (Mautic 7)

MCP server for Mautic 7 marketing automation (Columba Edition): campaigns, contacts,
segments, emails, forms, projects and business tools over Mautic v1 (FOSRestBundle)
and v2 (API Platform) endpoints.

Two images, one source tree:

| Image | Dockerfile | Transport | Purpose |
|---|---|---|---|
| `mantic-mcp` | `Dockerfile` | MCP stdio | CLI / agent clients (`docker run --rm -i`) |
| `mantic-mcp-http` | `Dockerfile.http` | MCP Streamable HTTP | Paperclip "connect with a link", remote clients (port `8090`) |

The HTTP image is self-contained (it builds the stdio server and the bridge in one
image) so each service can be built independently by Coolify.

## Build

```bash
docker build -t mantic-mcp:local .            # stdio
docker build -f Dockerfile.http -t mantic-mcp-http:local .
```

## Run

```bash
# stdio
docker run --rm -i --env-file .env mantic-mcp:local

# HTTP bridge
docker run --rm -p 8090:8090 --env-file .env mantic-mcp-http:local
curl -s http://127.0.0.1:8090/mcp   # JSON-RPC initialize
```

## Env

See `.env.example`. `MAUTIC_BASE_URL`, `MAUTIC_CLIENT_ID`, `MAUTIC_CLIENT_SECRET`,
`MAUTIC_TOKEN_ENDPOINT` are all required; the process exits immediately when any is
missing.

## Tools and API surface

68 baseline tools plus `get_instance_identity` (read-only), 69 in total.

### Campaign entry sources

`create_campaign_with_automation` can express exactly two entry sources:
`segments` (sent as campaign `lists`) and `forms`. A tag change
(`lead.changetags`) is an in-campaign decision, **not** an entry source, and this
server has no tag-trigger enrollment. A campaign that supplies only a tag-change
decision is rejected by the provider with `At least one contact source is
required`. `create_campaign` creates the campaign shell only and takes no entry
sources.

### Contact tags and custom fields

`customFields` is flattened into the top-level contact body for `create_contact`
and `update_contact` — no nested object is sent, because Mautic ignores unknown
nested keys while returning HTTP 200. `add_contact_tags` uses the contact edit
route (`PATCH /contacts/{id}/edit`) with the merged tag set, since Mautic has no
per-tag endpoint; it then reads the contact back and returns an error when a
requested tag did not persist. Tag writes are never reported as success without
that read-back.

### Instance identity

`get_instance_identity` reports the configured base host, the credential identity
returned by `GET /users/self`, and whether the `/api/v2` entrypoint answers. It
returns no tokens, headers or credential values. Mautic v1 exposes no version
endpoint, so `mauticVersion` stays `null` — identity is the credential-level proof
of which instance answered.

### API v2 tools

The six `*_project` tools are the only API v2 (API Platform) consumers. A provider
401/403/404 is reported as an explicit "Mautic API v2 is not available to this
credential" error naming the HTTP status — never as success, and never as an
unrelated failure. A v1 OAuth client is not automatically valid on `/api/v2`.

## Tests

```bash
npm ci
npm test        # tsc build + node --test
```

`test/` exercises the real handlers against a recording fake client, including the
negative controls (stale tag read-back, provider 401 on v2, secret leakage in the
identity payload). No additional test dependency is used.

## Provenance

Source of the running container (`mantic-mcp:latest` / `mantic-mcp-http:latest` on the
production host). Upstream inspiration: `Cbrown35/mantic-MCP`. The copy in this folder
is the deployed source of truth — upstream changes are applied here first.

## Worker (Cloudflare)

`worker/` = ten sam MCP jako Cloudflare Worker (`mantic-mcp.zariszlif.pl`):

- protokół MCP (JSON-RPC) obsłużony **ręcznie** — bez `@modelcontextprotocol/sdk`
  i bez `axios` (klient Mautic na `fetch`, `worker/src/mautic-client.ts`);
- bundle **68 KiB** (gzip 10 KiB) zamiast 1245 KiB z SDK + axios;
- narzędzia te same co w stdio (`src/tools/**`), błędy MCP przez `src/errors.ts`
  (bez zoda w bundlu) — serwer stdio tłumaczy je na SDK-owy `McpError`;
- deploy: `.github/workflows/mcp-workers.yml` (push do repo = build + `wrangler deploy`).

Konfiguracja Workera: `MAUTIC_BASE_URL`, `MAUTIC_TOKEN_ENDPOINT` (vars) +
`MAUTIC_CLIENT_ID`, `MAUTIC_CLIENT_SECRET`, `MCP_AUTH_TOKEN` (sekrety).
