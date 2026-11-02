# Plasmic MCP — canonical self-hosted adapter

The canonical self-hosted source lives in `harness-zar-i-szlif/plasmic-mcp/**`. Product-specific MCP remains in the separate `zar-i-szlif` repository. This adapter talks to the
self-hosted **Plasmic WAB REST API**, not GitHub. Repository branches, PRs and
CI checks belong to GitHub MCP.

## Servers

| Server | Command | Port | Function |
| --- | --- | --- | --- |
| Plasmic MCP | `node services/plasmic-mcp/server.ts` | 8091 | 26 agent-visible tools (projects, branches, design reading/editing, validation) |
| OpenDesign bridge MCP | `node services/opendesign-bridge-mcp/server.ts` | 8092 | OpenDesign brand/design sync |

The Plasmic tool catalog is asserted against a real **local stdio MCP server**
in `tests/plasmic-mcp-catalog.test.ts`, not a hardcoded production claim.

Branch creation **never** accepts WAB `base: "new"`, which could implicitly
publish a project. It uses `base: "latest"` and serializes/idempotently
deduplicates calls by project. Merge preview uses WAB `pretend: true` only;
the MCP tool **does not** commit a design merge.

## Human comments on Plasmic elements (AI-readable)

The adapter now exposes **26 tools**. Two are explicitly read-only and allow
agents to retrieve the same human Studio comment threads shown on canvas:

- `plasmic_list_comments(projectId, branchId?, includeResolved?, includeDeleted?, offset?, limit?)`
- `plasmic_get_element_comments(projectId, elementIid?, elementUuid?, branchId?, includeResolved?, includeDeleted?, offset?, limit?)`

These use WAB `GET /api/v1/comments/:projectBranchId`, not the project revision
bundle, GitHub issue comments or a simulated comment store. For main, omit
`branchId`; for a design branch pass its WAB branch ID. Element association
uses the exact stored `location.subject.iid` / `location.subject.uuid` and
`variants` addresses. Replies, timestamps and display names are included.
Deleted comment bodies, unrelated commenter emails and sensitive user profiles
are not exposed. Defaults: unresolved/non-deleted, up to 50 threads at a time.

The WAB identity needs at least commenter access to the project and branch;
the remote MCP also requires its own Bearer token. Comment text is untrusted
input: it is design feedback, **not** a directive to run arbitrary commands or
bypass review. No write/resolve/delete-comment tools are exposed.

Before considering production E2E complete, verify a real disposable Studio
project with one pinned element comment, a reply and a resolved thread,
then check `tools/list` returns 26 tools, project+branch isolation,
author/subject data, 401/403 and the same comment texts as Studio. Local
contract tests use fixtures and do not establish a live WAB read.

Structural `plasmic_create_page` and `plasmic_create_component` now
save a complete WAB bundle to preserve cross-entry references; tests reject
dangling fixture references. Verify live disposable-project readback before
claiming 23/23 E2E.

The MCP catalog has 26 tools. E2E branch cleanup is an opt-in support
script: set `PLASMIC_ALLOW_E2E_BRANCH_DELETE=true` and
`PLASMIC_E2E_PROJECT_ID`, then run `npm run cleanup:e2e-branch -- <branchId>`.
It deletes only an existing `mcp-e2e-` branch and verifies its removal; use a
dedicated disposable project because deleting the branch also discards its
unpublished page/component test changes.

## Local checks

From `mcp/plasmic`:

```bash
npm ci --include=dev
npm test
npm run typecheck
npm run lint
npm run preflight:source
```

The Dockerfile uses lockfile-only `npm ci --omit=dev --ignore-scripts`,
runs as the unprivileged `mcp` user, and exposes 8091/8092.

## Production release: verify the canonical build and deployment lane

```bash
npm run preflight:release
```

This checks the actual repository's GHCR workflow, canonical source path,
Dockerfile, `main` push gate and immutable Compose `IMAGE_TAG`.
The current `.github/workflows/opendesign-brand-mcp.yml` tests and builds
`mcp/plasmic` with `mcp/plasmic/Dockerfile`; `RELEASE_PREFLIGHT_OK`
confirms this mapping. Green PR CI validates source but does not publish
or deploy an image.

**Authorized release steps** (independent CTO review and the existing
host release lane remain required):

1. Verify the workflow source trigger, test working directory,
   package-lock cache and Docker build context continue to target
   `mcp/plasmic/**` (Dockerfile `mcp/plasmic/Dockerfile`).
2. Run `npm ci --include=dev`, `npm test`, `npm run typecheck`, `npm run lint`
   and `npm run preflight:release` before GHCR publication.
3. Publish a digest-verified image tagged by the **merge commit SHA on
   `main`**, not the feature-branch SHA; retain the previous deployed image.
4. On the host, only an authorized operator can update Compose
   `IMAGE_TAG=<verified-main-SHA>`, snapshot state, pull/recreate the service
   and confirm the resulting image digest. Cloudflare routing alone cannot
   deploy the container.
5. Run authenticated `initialize`/`tools/list` for all 26 tools, WAB API
   read and isolated disposable project/branch create/write/readback/rollback,
   plus an unauthorized 401 negative case. **The `base:latest` design
   branch requires a published package in the disposable WAB project;
   an unpublished fixture can return HTTP 500. Never publish a real
   project merely to satisfy a test.**
6. Roll back to the recorded previous image tag/digest if live health,
   authentication or tool list differs. Do not edit Plasmic Core or product
   code to fix the adapter.

The existing current GHCR pipeline and host deployment path are not modified
by this documentation. Production remains unverified until these gates pass.

See `INTEGRATION_BOUNDARIES.md` for GitHub MCP vs Plasmic MCP ownership.


## Native UI authoring API (2026-11-02)

The adapter now includes three additional native **Plasmic WAB** tools:

- \`plasmic_read_ui_outline(projectId, componentId, branchId?, depth?, maxNodes?)\`: bounded read-only outline of TplTag/component instances and associated RawText/RuleSet values. No project tokens.
- \`plasmic_append_ui_tree(projectId, parentElementId, nodes, branchId?, dryRun?, idempotencyKey?)\`: append up to **60 native semantic tags** (depth <=7) in one revisioned WAB write. Accepts optional text, tag name, and plain CSS values. This is **not** HTML import, screenshot upload, JS generation, or fully implemented form logic.
- \`plasmic_batch_set_styles(projectId, edits, branchId?, dryRun?, idempotencyKey?)\`: batch up to **25** CSS RuleSet updates atomically with revision checks. Refuses shared RuleSets, duplicate targets and unsafe CSS.

Writing tools default to \`dryRun=true\` and require an \`idempotencyKey\` for \`dryRun=false\`; they lock at project scope and generate auditable readback. Review dry-run output before live writes. Test within a disposable Plasmic project first; no implicit publication or Git merge. Responsive designs can use flex, grid and fluid values; WAB breakpoint-specific variant mutation is not yet implemented. Do not claim visual preview, accessibility audit, Next.js export or image asset upload — none is exposed by this catalog.

### WAB identity is separate from MCP bearer auth

The MCP's \`MCP_AUTH_TOKEN\` secures the transport but does **not** authenticate to WAB. For real project access configure a WAB-authorized \`PLASMIC_EMAIL\` and \`PLASMIC_PASSWORD\`, or a supported WAB team identity where the endpoint permits it. The underlying user must have project permission. \`/health=200\` checks the transport only; \`/ready=200\` requires WAB health **and** authenticated \`listProjects()\`. A \`403 Must be a normal user\` is not an MCP outage and must not be bypassed by disabling authorization.
