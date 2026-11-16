# Plasmic MCP — canonical self-hosted adapter

The canonical self-hosted source lives in `harness-zar-i-szlif/plasmic-mcp/**`. Product-specific MCP remains in the separate `zar-i-szlif` repository. This adapter talks to the
self-hosted **Plasmic WAB REST API**, not GitHub. Repository branches, PRs and
CI checks belong to GitHub MCP.

## Servers

| Server | Command | Port | Function |
| --- | --- | --- | --- |
| Plasmic MCP | `node services/plasmic-mcp/server.ts` | 8091 | 30 agent-visible tools (projects, branches, catalog, composition, design reading/editing, validation) |
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
then check `tools/list` returns 30 tools, project+branch isolation,
author/subject data, 401/403 and the same comment texts as Studio. Local
contract tests use fixtures and do not establish a live WAB read.

Structural `plasmic_create_page` and `plasmic_create_component` now
save a complete WAB bundle to preserve cross-entry references; tests reject
dangling fixture references. Verify live disposable-project readback before
claiming 23/23 E2E.

The MCP catalog has 30 tools. E2E branch cleanup is an opt-in support
script: set `PLASMIC_ALLOW_E2E_BRANCH_DELETE=true` and
`PLASMIC_E2E_PROJECT_ID`, then run `npm run cleanup:e2e-branch -- <branchId>`.
It deletes only an existing `mcp-e2e-` branch and verifies its removal; use a
dedicated disposable project because deleting the branch also discards its
unpublished page/component test changes.

## Component catalog and MCP-only composition (ZARI-229)

Four tools make the adapter a usable component library and composition engine
without any agent bypassing MCP for WAB REST/Studio calls:

- `plasmic_search_components(projectId, branchId?, query?, kind?, limit?, offset?)`
  — paginated catalog of pages/components with stable ids, instance counts,
  declared param names and a `catalogKey` derived from
  `project@branch#revision`. The index cache is revision-scoped, so a served
  index can never be older than the revision read in the same call.
- `plasmic_get_component_spec(projectId, componentId, branchId?)` — declared
  params (with resolvable type names), slots, instances, subtree dependencies
  and referenced style tokens for one component of the live revision.
  `previewAvailable` is `false`: this adapter exposes no preview URL instead of
  inventing one, and `slotsAvailable` reports when the revision carries no
  resolvable param types.
- `plasmic_plan_composition(projectId, parentElementId, items, index?, branchId?)`
  — read-only plan: validates the parent container, every component id, prop
  declarations and the insertion index, then returns the exact entries and
  order that a write would create.
- `plasmic_compose_components(...)` — the same plan applied in one
  revision-safe `mutate()` (`saveMode: "full"`). `dryRun` defaults to `true`;
  a live write requires `idempotencyKey`. Entry ids are derived from the
  operation key, so a retry is a no-op instead of a duplicate node.

Composition builds each instance by cloning an existing instance of that
component, then gives the clone **private** `VariantSetting`, `RuleSet`, attrs
and param args, and wires it into the parent's `children` at the requested
index. The previous behaviour shared those entries with the template instance
(editing the clone silently restyled the original) and left the clone
unreferenced by any parent (unreachable in Studio).

Reported limitations — these fail with a structured error instead of a fake
success: slot routing by slot name, responsive variant overrides, components
with no instance in the revision (`NO_INSTANCE_TEMPLATE`), templates carrying
slot content (`SLOT_CONTENT_CLONE_UNSUPPORTED`), page components as child
instances, and props whose name is not a declared component param
(`PROP_UNSUPPORTED`).

Local fixture tests prove the contract (`tests/plasmic-catalog-compose.test.ts`).
They do **not** prove a live WAB write: an authenticated disposable-project
compose/readback/rollback canary is still required before claiming DOD-05.

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
5. Run authenticated `initialize`/`tools/list` for all 30 tools, WAB API
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

## State volume ownership (/state)

The image runs as the unprivileged `mcp` user (uid/gid **10001**) with a
read-only root filesystem; only the `plasmic_mcp_state` volume mounted at
`/state` is writable. The image creates `/state` owned by `mcp` so a **new**
volume inherits that owner.

A volume created by an earlier root-running image stays `root:root`, and the
first state write (`plasmic_get_changes` seen marker, audit log, project lock)
then fails with `EACCES`.

The `chown` must cover **every descendant**, not only the mount root. A legacy
volume already holds `root`-owned children — `/state/seen/<project>__main.json`
(seen markers), `/state/locks` (project locks) and `audit.jsonl` — and the MCP
process needs write access to those files and directories, not merely to
`/state`. `chown 10001:10001 /state` alone leaves them root-owned, so the same
`EACCES` comes back on the first `get_changes` even though the documented
"fix" was applied.

### Migrating a populated volume (host owner, once)

Chowning a directory tree under a live writer races with it and can leave
half-owned state, so the service must be **stopped and verified stopped**, and
the volume **backed up and the archive verified**, before any ownership change.
The block below is fail-fast: `set -euo pipefail` plus explicit guard checks
mean a failed stop, a missing volume mapping or a missing backup archive aborts
the procedure **before** `chown` runs. Do not strip the guards to "get it done".

```bash
set -euo pipefail

# 0. resolve the exact container and the volume it really mounts at /state
CONTAINER=<container id or name>        # find it: docker ps --filter name=plasmic-mcp
STATE_VOLUME=<state volume name>
BACKUP_DIR=<absolute host path with free space>

# 1. verify the binding before touching anything: the container must exist,
#    must mount a volume at /state, and it must be THIS volume
docker inspect --type container "$CONTAINER" >/dev/null
MOUNTED=$(docker inspect --type container \
  -f '{{range .Mounts}}{{if eq .Destination "/state"}}{{.Name}}{{end}}{{end}}' "$CONTAINER")
if [ -z "$MOUNTED" ]; then
  echo "container $CONTAINER mounts no volume at /state — aborting" >&2
  exit 1
fi
if [ "$MOUNTED" != "$STATE_VOLUME" ]; then
  echo "container $CONTAINER mounts $MOUNTED at /state, not $STATE_VOLUME — aborting" >&2
  exit 1
fi
docker volume inspect "$STATE_VOLUME" >/dev/null

# 2. stop writers, then PROVE the container is stopped
docker stop "$CONTAINER"
if [ "$(docker inspect --type container -f '{{.State.Running}}' "$CONTAINER")" != "false" ]; then
  echo "container $CONTAINER is still running — aborting before touching the volume" >&2
  exit 1
fi

# 3. back up, then PROVE the archive exists and is not empty
mkdir -p "$BACKUP_DIR"
ARCHIVE="$BACKUP_DIR/plasmic_mcp_state-$(date +%Y%m%dT%H%M%S).tgz"
docker run --rm -v "$STATE_VOLUME":/state -v "$BACKUP_DIR":/backup alpine \
  tar czf "/backup/$(basename "$ARCHIVE")" -C /state .
if [ ! -s "$ARCHIVE" ]; then
  echo "backup archive $ARCHIVE is missing or empty — aborting before chown" >&2
  exit 1
fi

# 4. only now: fix ownership of the whole tree, not the mount root
docker run --rm -v "$STATE_VOLUME":/state alpine chown -R 10001:10001 /state

# 5. verify every descendant, not just /state
docker run --rm -v "$STATE_VOLUME":/state alpine sh -c '
  bad=$(find /state \( ! -user 10001 -o ! -group 10001 \) -print)
  if [ -n "$bad" ]; then
    echo "still not owned by 10001:10001:" >&2
    echo "$bad" >&2
    exit 1
  fi'

# 6. start the service again and check /ready (the stateDir check must pass)
docker start "$CONTAINER"
```

If the stack is Compose-managed, use this procedure instead. It is **complete on
its own** — do not splice it with the block above, which targets a single
container ID and would leave `$CONTAINER` undefined. It performs the same
binding check, the same backup-then-verify, and the same ownership verification,
with a Compose-scoped stop:

```bash
set -euo pipefail

COMPOSE_PROJECT=<compose project>       # docker compose ls
COMPOSE_SERVICE=<service name>          # docker compose -p "$COMPOSE_PROJECT" config --services
STATE_VOLUME=<state volume name>
BACKUP_DIR=<absolute host path with free space>

# 1. binding check: find the container Compose actually runs for this service,
#    and prove it mounts THIS volume at /state before anything is touched
if ! IDS=$(docker compose -p "$COMPOSE_PROJECT" ps --all --quiet "$COMPOSE_SERVICE"); then
  echo "cannot enumerate containers for $COMPOSE_PROJECT/$COMPOSE_SERVICE — aborting" >&2
  exit 1
fi
CONTAINER=$(printf '%s\n' "$IDS" | head -n1)
if [ -z "$CONTAINER" ]; then
  echo "no container for $COMPOSE_PROJECT/$COMPOSE_SERVICE — aborting" >&2
  exit 1
fi
MOUNTED=$(docker inspect --type container \
  -f '{{range .Mounts}}{{if eq .Destination "/state"}}{{.Name}}{{end}}{{end}}' "$CONTAINER")
if [ -z "$MOUNTED" ]; then
  echo "service container $CONTAINER mounts no volume at /state — aborting" >&2
  exit 1
fi
if [ "$MOUNTED" != "$STATE_VOLUME" ]; then
  echo "service container mounts $MOUNTED at /state, not $STATE_VOLUME — aborting" >&2
  exit 1
fi
docker volume inspect "$STATE_VOLUME" >/dev/null

# 2. stop writers, then PROVE it — a `compose ps` error is NOT evidence that the
#    service is stopped, so a failed query aborts instead of falling through
docker compose -p "$COMPOSE_PROJECT" stop "$COMPOSE_SERVICE"
if ! RUNNING=$(docker compose -p "$COMPOSE_PROJECT" ps --status running --services); then
  echo "cannot verify that $COMPOSE_SERVICE is stopped — aborting" >&2
  exit 1
fi
if printf '%s\n' "$RUNNING" | grep -qx "$COMPOSE_SERVICE"; then
  echo "$COMPOSE_SERVICE is still running — aborting before touching the volume" >&2
  exit 1
fi

# 3. back up, then PROVE the archive exists and is not empty
mkdir -p "$BACKUP_DIR"
ARCHIVE="$BACKUP_DIR/plasmic_mcp_state-$(date +%Y%m%dT%H%M%S).tgz"
docker run --rm -v "$STATE_VOLUME":/state -v "$BACKUP_DIR":/backup alpine \
  tar czf "/backup/$(basename "$ARCHIVE")" -C /state .
if [ ! -s "$ARCHIVE" ]; then
  echo "backup archive $ARCHIVE is missing or empty — aborting before chown" >&2
  exit 1
fi

# 4. only now: fix ownership of the whole tree, not the mount root
docker run --rm -v "$STATE_VOLUME":/state alpine chown -R 10001:10001 /state

# 5. verify every descendant, not just /state
docker run --rm -v "$STATE_VOLUME":/state alpine sh -c '
  bad=$(find /state \( ! -user 10001 -o ! -group 10001 \) -print)
  if [ -n "$bad" ]; then
    echo "still not owned by 10001:10001:" >&2
    echo "$bad" >&2
    exit 1
  fi'

# 6. start the service again and check /ready (the stateDir check must pass)
docker compose -p "$COMPOSE_PROJECT" start "$COMPOSE_SERVICE"
```

In both variants the rule is the same: a command whose **success you have not
observed** is a failure. Do not replace the guard checks with `|| true`, a bare
`&&` list, or a pipeline whose exit status you discard — under `set -e` those
turn "could not verify" into "verified safe".

### New or empty volume

Nothing to migrate: the image creates `/state` owned by `mcp` before dropping
privileges, so a fresh volume inherits `10001:10001`. Do not run the `chown`
steps above on a fresh volume; verify with `/ready` instead.

If the platform creates the volume itself (root-owned), the same recursive
`chown` applies — with the service stopped and a backup taken — before the
first start that writes state.

The server does not disable the seen marker or skip auditing on a read-only
state dir. It logs `STATE_DIR not writable` at start, reports it as a failing
check on `/ready`, and every state-writing tool fails with
`STATE_DIR_UNWRITABLE (<tool>): EACCES: <path> must be owned by the container
user (uid 10001 / mcp); ...` instead of a bare `EACCES`.
