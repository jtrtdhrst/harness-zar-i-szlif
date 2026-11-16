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

68 baseline tools plus `get_instance_identity` (read-only) and
`provision_inactive_test_campaign` (dedicated-TEST graph fixture), 70 in total.

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

## Write guard (SECURITY GATE v2)

Provider mutations are **denied by default** at the transport boundary
(`dispatchTool`), not in an agent prompt. Every tool is classified explicitly:
`read` passes, six `test-write` tools are the only grantable mutations, and
every other mutation is refused unconditionally. An unclassified tool name is
denied as a mutation, so a tool added later cannot become writable by accident.

| Class | Tools | Behaviour |
| --- | --- | --- |
| `read` | all `list_*`, `get_*`, `search_contacts`, `get_form_submissions`, `get_segment_contacts`, `get_contact_activity`, `list_contact_fields`, `export_campaign`, `get_instance_identity` (34) | unchanged, no grant needed |
| `test-write` | `create_contact`, `update_contact`, `delete_contact`, `add_contact_tags`, `create_tag` (5) | allowed only under a matching TEST-only grant |
| `test-write` + **dedicated deployment** | `provision_inactive_test_campaign` (1) | additionally requires `MAUTIC_DEPLOYMENT_CLASS=dedicated-test`; stays denied on the shared transport |
| `denied` | send, campaign execute/create/clone/import, enrollment, segment/email/content/company/note/points/stage/webhook/file/report and API v2 project mutations (30) | never granted in this build, even if listed |

### Inactive test graph (`provision_inactive_test_campaign`)

The only way to create a campaign/segment/template, and it creates exactly one
inert shape per call: an unpublished email template (`emailType: "template"`,
`isPublished: false`), an unpublished segment filtered on one granted tag
(documented filter form `{glue, field: "tags", object: "lead", type: "text",
operator: "like", properties: {filter}}`), and an unpublished campaign whose
**only** contact source is that segment (`lists: [{id}]`, no events). The
campaign's entry source is the segment — a supported Mautic campaign source; a
tag-change decision is an in-campaign event and is **not** an entry source, and
this server never claims tag-triggered enrollment.

It accepts five arguments and **refuses** anything else (`isPublished`,
`publishUp/Down`, `events`, `lists`, `contactIds`, `recipients`, `send`,
`activate`, `id`, `emailId`, `campaignId`, `segmentId`) before touching the
provider, so activation cannot be smuggled in through an unexpected key. Names
must start with a granted `allowedFixturePrefixes` entry and the tag with a
granted `allowedTagPrefixes` entry. Every object is read back: a resource that
persisted published, a campaign whose source list does not reference the new
segment, an unexpected campaign event or a missing id fails the call instead of
reporting success. Entry/duplicate/suppression behaviour with real contacts is
**not run** here and is listed in the response as such.

**Deployment gate:** the shared stdio/HTTP provider carries no trusted per-agent
identity, so graph creation is refused there with `SHARED_TRANSPORT_DENIED` even
with a valid grant. Enabling it requires an operator-provisioned,
single-principal **dedicated TEST deployment** (`MAUTIC_DEPLOYMENT_CLASS=dedicated-test`)
with its own pinned host/tenant/principal and a short-lived TEST grant. Until such
a deployment exists this is an infrastructure gate for the owner, not a code gap —
the general `create_campaign*`, `create_segment` and `create_email_template`
tools stay permanently denied.

A `test-write` call is authorized only when **all** of these hold:

1. `MAUTIC_TARGET_HOST` equals the host of `MAUTIC_BASE_URL`;
2. `MAUTIC_PRINCIPAL` equals the username or e-mail that the provider itself
   returns from `GET /users/self` (a probe, not a self-reported value; cached for
   `MAUTIC_WRITE_GUARD_IDENTITY_TTL_MS`, default 60 s);
3. `MAUTIC_TARGET_TENANT` equals the grant's `tenant`;
4. the grant is `scope: "test-only"`, lists the tool, and has not expired;
5. the resource is in scope:
   - **tags** are read through the same normalisation the payload builder uses
     (`flattenContactPayload` / `normalizeTagList`), so every accepted input form
     — array of strings, `{tag}` objects, comma-separated string, object map — is
     scope-checked before it can reach the provider; every tag must start with
     one of `allowedTagPrefixes`;
   - **the target contact** is resolved at the provider (`GET /contacts/{id}`) for
     `update_contact`, `delete_contact` and `add_contact_tags`, and its **real**
     e-mail must match one of `allowedContactEmails`. A requested e-mail is never
     used as evidence of target identity, an unreadable target is a denial, and a
     target with no verifiable e-mail is a denial;
   - an **address being written** must also be in scope, so a fixture contact
     cannot be moved onto a real customer address.

A refusal throws a typed `McpError` whose `data` is
`{error: "WRITE_GUARD_DENIED", reason, tool, targetHost, ...}` — sanitized, with
no grant content, token, header or credential value. Reasons:
`NO_GRANT`, `GRANT_INVALID`, `GRANT_EXPIRED`, `TENANT_MISMATCH`, `HOST_MISMATCH`,
`PRINCIPAL_MISMATCH`, `IDENTITY_UNAVAILABLE`, `TOOL_NOT_GRANTED`,
`SCOPE_VIOLATION`, `TOOL_DENIED`, `UNKNOWN_TOOL`.

Env contract: see `.env.example`. Empty `MAUTIC_WRITE_GRANT` = read-only, which
is the intended default. The grant is operator policy in the deployment
environment; it is never committed, never read from tool arguments or issue
comments, and carries no provider credential.

**What this does not enforce, by design and by scope:**

- **Per-agent principals.** The stdio/HTTP MCP transport has no trusted actor
  identity: one server process serves whichever agent connects. Scoping is
  therefore per *deployment* (one grant per deployed instance), which is why a
  grant must never be placed on a shared instance. A per-actor binding needs an
  operator-side principal or a per-agent deployment.
- **Stop control.** Cancelling a run (`issue cancel-task`) or steering an agent
  is a runtime capability outside this package; a mid-run comment is not a stop
  guarantee. The guard limits what a run can do, not when it stops.
- **The Cloudflare Worker** (`worker/`) reuses `src/tools/**` but passes no guard
  and has no `getBaseUrl`, so its writes are denied too (fail-closed). Wiring a
  grant there needs `worker/**` and is out of this issue's scope.

**Rollback:** unset `MAUTIC_WRITE_GRANT` (or redeploy the previous image). Both
return the service to its prior behaviour immediately; no data migration, no
state, no schema.

## Tests

```bash
npm ci
npm test        # tsc build + node --test
```

`test/` exercises the real handlers against a recording fake client, including the
negative controls (stale tag read-back, provider 401 on v2, secret leakage in the
identity payload) and the write guard's fail-closed matrix: no grant, invalid or
expired grant, tenant/host/principal mismatch, unverifiable identity, tool not
granted, out-of-scope tag/recipient, unclassified tool, and send/activation tools
listed in a grant — each asserted to reach the provider **zero** times. No
additional test dependency is used.

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
