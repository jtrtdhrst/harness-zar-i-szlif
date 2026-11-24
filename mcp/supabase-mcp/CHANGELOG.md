# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- **Least-privilege tool policy (fail closed)**
  - Unknown JWT roles now receive **no** tool privileges; the previous fallback to
    `authenticated` (which granted `regular` access) is removed.
  - Tokens without a non-empty string `role` claim are rejected with `401` instead of
    being treated as `authenticated`.
  - New `sensitive` privilege level for user data, PII, log contents, storage objects,
    function source and connection activity. `authenticated` callers are limited to
    schema metadata; `list_auth_users`, `get_auth_user`, `get_logs`,
    `list_edge_function_logs`, `list_storage_objects`, `get_edge_function_details`,
    `get_database_connections` and `get_cron_job_history` moved out of `regular`.
  - `privilegeLevel` is now required: tools without a declared level are refused at
    registration/call time instead of defaulting to `regular`. The tool list moved to
    `src/tools/registry.ts` so the policy is testable in one place.
- **Typed DDL surface `add_nullable_column`**: operator-pinned schema allowlist
  (`SUPABASE_MCP_DDL_SCHEMA_ALLOWLIST`), reserved-schema deny list, strict identifier and
  type validation, single transaction with `information_schema` readback, rollback by
  default. Requires `DATABASE_URL`; never uses a service_role JWT.
  - Readback is verified against the request before success is reported (column name,
    `data_type`, `is_nullable = YES`, no default). `ADD COLUMN IF NOT EXISTS` silently
    no-ops on an existing column, so a pre-existing column of another type, a `NOT NULL`
    column or a defaulted column now fails the call and rolls back instead of being
    reported as applied.

### Added

- **HTTP Transport Mode**: Run MCP server in HTTP mode for Docker/Kong integration
  - Express-based HTTP server with Streamable HTTP Transport
  - Configurable CORS, rate limiting, and request timeouts
  - Health check endpoint for container orchestration
- **JWT Authentication Middleware**: Validate Supabase JWTs in HTTP mode
- **Privilege-Based Access Control**: Role-based tool access (regular, privileged)
  - `service_role`: Access to all tools
  - `authenticated`/`anon`: Access to regular tools only
- **24 New Database Introspection Tools**:
  - Schema: `list_table_columns`, `list_indexes`, `list_constraints`, `list_foreign_keys`, `list_triggers`, `list_database_functions`, `list_available_extensions`
  - Security: `list_rls_policies`, `get_rls_status`, `get_advisors`
  - Definitions: `get_function_definition`, `get_trigger_definition`
  - Performance: `get_index_stats`, `get_vector_index_stats`, `explain_query`
  - Extensions: `list_cron_jobs`, `get_cron_job_history`, `list_vector_indexes`
  - Edge Functions: `list_edge_functions`, `get_edge_function_details`, `list_edge_function_logs`
  - Storage: `get_storage_config`, `update_storage_config`
  - Logs: `get_logs`
- **Bun Runtime**: Migrated from Node.js/npm to Bun for faster builds and execution
- **Comprehensive Test Suite**: 13 test files with 240+ passing tests
- **Docker Integration**: Dockerfile and Docker Compose configuration for self-hosted Supabase stacks

### Changed

- `execute_sql` now requires `service_role` JWT in HTTP mode (privileged tool)
- Replaced `package-lock.json` with `bun.lock`

### Removed

- **`get_anon_key` tool**: Removed to prevent exposure of sensitive API keys through MCP
- **`get_service_key` tool**: Removed to prevent exposure of sensitive API keys through MCP

### Security

- Removed tools that exposed API keys (`get_anon_key`, `get_service_key`)
  - **Rationale**: MCP tools can be called by any connected client. Exposing API keys through MCP creates a security risk where keys could be extracted by malicious or compromised MCP clients. The anon key and service role key are already available to the server at startup via environment variables or CLI arguments - there's no legitimate use case for retrieving them via MCP during runtime.
- Added privilege-based access control to restrict sensitive operations to `service_role` only
- JWT authentication enforced for all HTTP mode requests
