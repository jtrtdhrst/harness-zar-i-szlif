# Supabase MCP (self-hosted)

> **Źródło tej usługi Coolify:** repo `jtrtdhrst/harness-zar-i-szlif`, UUID `tjit4c8m0kjh8brkmdhyvkde`; katalog `mcp/supabase-mcp/`; Dockerfile `mcp/supabase-mcp/Dockerfile`; implementacja: `src/`.
> Kod jest w tym folderze; bieżąca produkcyjna wersja musi być potwierdzona digestem i pozytywnym E2E.


MCP server for a **self-hosted** Supabase instance: 50+ database management tools
(schemas, tables, migrations, SQL execution, extensions, types, functions, policies,
roles) over PostgREST/Kong and direct Postgres.

- Source: `src/` (TypeScript), built with `bun run build` → `dist/index.js`.
- `Dockerfile` — bun runtime, non-root user `mcp`, healthcheck on `:3100/health`.

## Build

```bash
docker build -t selfhosted-supabase-mcp:local .
docker run --rm -p 3100:3100 --env-file .env selfhosted-supabase-mcp:local
```

The server speaks MCP Streamable HTTP on `:3100/mcp` (transport `http`).

## Deploy

`docker-compose.yml` expects the Supabase stack to be up and to publish the
`supabase_default` network (`docker compose` from the Supabase repo). The MCP server
reaches PostgREST/Kong through `SUPABASE_URL` and Postgres through `DATABASE_URL`.

## Authorization

HTTP mode (`/mcp`) requires a Supabase JWT signed with `SUPABASE_AUTH_JWT_SECRET`. The
token's `role` claim selects the tool privilege level; tools are classified in
`src/tools/registry.ts` and the policy lives in `src/tools/types.ts`:

| privilege level | content | `service_role` | `authenticated` | `anon` | unknown role |
| --- | --- | --- | --- | --- | --- |
| `regular` | schema/structure metadata (tables, columns, indexes, policies, extensions) | yes | yes | no | no |
| `sensitive` | user data and PII (`list_auth_users`, `get_auth_user`), log contents (`get_logs`, `list_edge_function_logs`), storage objects, function source, connection activity | yes | no | no | no |
| `privileged` | mutations and admin: `execute_sql`, `apply_migration`, auth-user admin, config changes, `add_nullable_column` | yes | no | no | no |

Fail-closed rules:

- An unknown role gets **no** privileges. Roles must be added explicitly to
  `ROLE_PRIVILEGE_MAP`; there is no fallback to `authenticated`.
- A token without a (non-empty, string) `role` claim is rejected with `401`.
- A tool that does not declare a `privilegeLevel` is refused at registration and at call
  time; nothing defaults to `regular`.

`add_nullable_column` is the only DDL surface. It is disabled unless an operator pins
`SUPABASE_MCP_DDL_SCHEMA_ALLOWLIST` (comma-separated schema names), always refuses
reserved schemas (`auth`, `storage`, `pg_catalog`, ...), only adds nullable columns of an
allowlisted type, and defaults to verifying the change and then rolling the transaction
back. Verification compares the `information_schema` readback with the request — column
name, type, `is_nullable = YES` and no default — because `ADD COLUMN IF NOT EXISTS`
no-ops when the name already exists; a pre-existing column with a different definition
therefore fails the call instead of being reported as applied. It requires `DATABASE_URL`
and never uses a service_role JWT.

## Provenance

Upstream: <https://github.com/HenkDz/selfhosted-supabase-mcp> (MIT, `main`,
package version 1.2.0). The `Dockerfile` in this folder reproduces the deployed
`selfhosted-supabase-mcp:latest` image (upstream ships a Node/smithery Dockerfile
instead).
