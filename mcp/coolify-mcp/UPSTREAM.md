# Owned Coolify MCP source

The full upstream source code, tests, and MIT license are vendored at
`mcp/coolify-mcp/` from `StuMason/coolify-mcp` tag `v3.10.1`,
Git commit `efce1d2110541d0ecf8b6185fd44c412042d2ca4`.
Do not use unpinned upstream tags or auto-update these files.

`mcp/coolify-mcp/Dockerfile` builds from the owned `mcp/coolify-mcp/` directory.
Build context MUST be `mcp/coolify-mcp/`; Dockerfile path is `Dockerfile`.
Release tools are opt-in via `COOLIFY_ZIS_RELEASE_TOOLS=true`.

The new release tools (`release_catalog`, `release_inventory`,
`release_status`, `release_drift`, `release_preflight`) are read-only.
The immutable source SHA/image catalog is an operator-mounted JSON file
named by `COOLIFY_RELEASE_CATALOG_FILE`, with mode 0644 or stricter,
no symlinks, no group/world write. Never put API tokens in that file.
Catalog image references are mandatory `@sha256` pins, not mutable tags.

No tool in this module bypasses the existing root-owned
`harness-image-delivery` controller, independent review, HOLD state,
Coolify production readback, MCP functional E2E, or rollback.
`CONFIG_MATCH_ONLY_NOT_DONE` explicitly means live container
image/SHA and production E2E were NOT verified.

Validation (from coolify-mcp):
```bash
npm ci --ignore-scripts
npm run build
npm test -- --runInBand
npm run lint
```

Production must NOT be switched from the current external image
until this exact source is independently reviewed, CI passes,
the owned image is published at a digest, and an authorized
canary proves OAuth, MCP tools, HTTP, configuration safety,
negative authorization and rollback.

The upstream marketing preview PNG docs/assets/social-preview.png is intentionally excluded; it is not application source, a build input, or test fixture.

## Existing production migration compatibility (2026-11-22)

The live 3.9.0 Compose service uses the persistent OAuth state volume at `/data`,
owned by UID/GID 1000, and a legacy host bind mount overriding
`/app/dist/lib/oauth.js`. The owned image intentionally runs as the standard
Node.js Alpine `node` user (UID 1000) to retain write access to the state
volume without changing ownership. The ChatGPT CIMD public-client PKCE
compatibility patch previously supplied by the mounted 3.9.0 JavaScript file
is now implemented in `src/lib/oauth.ts`, with positive and negative tests.

**Cutover precondition:** authorized release must remove the obsolete
`/app/dist/lib/oauth.js` bind mount before switching to the owned image,
otherwise it would shadow the newly reviewed compiled OAuth module. Preserve
`/data`, OAuth state, existing token configuration, endpoint and rollback
image. Confirm exact SHA/digest and live authenticated + unauthorized E2E.
Do not remove either mount or touch production under HOLD.
