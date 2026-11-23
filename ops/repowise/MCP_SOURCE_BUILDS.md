# MCP source-to-image build contract — Harness (2026-11-23)

**Owner and source of truth:** `jtrtdhrst/harness-zar-i-szlif`, protected `main`. This is a **source/build contract**, not an assertion that any particular release was promoted. RepoWise must answer questions about MCP build sources from the versioned mappings below, not from inferred names, stale wiki pages or Coolify Git metadata.

## Mandatory rule for every source-owned MCP

1. Source code, lockfiles, Dockerfile and tests live in one canonical `mcp/<service>/` directory. All Docker `COPY` inputs must be inside that service's own build context; no repo-root fallback, ghost source folders or unreviewed vendor binaries.
2. An exact, reviewed GitHub `main` SHA builds through its assigned workflow (table below). PR validation uses the exact PR SHA and must not run untrusted PR workflow code on a production-adjacent self-hosted runner.
3. OCI image must include `org.opencontainers.image.source` and `org.opencontainers.image.revision`, be published to GHCR with an exact `sha-<40-char-commit>` tag, and its **registry manifest digest** must be recorded. An image ID or floating tag is not a release digest.
4. Publishing is not deployment. Production Coolify uses only the authorized immutable `image@sha256:...`; do not auto-promote on push or alter persistent volumes/OAuth state. Preserve CTO exact-SHA review, COO release authorization, CI verification, approved per-service UUID, production digest readback, positive/negative MCP E2E and rollback.
5. RepoWise indexes Git source facts and reviewed docs; running image SHA/digest, deployment state and ChatGPT MCP behavior require independent runtime evidence. Answer **UNKNOWN / NOT VERIFIED** when missing.

## Current 12 source-owned MCPs

Every row below is derived from `ops/coolify-service-registry.json` and `ops/service-build-roots.json` and enforced by `scripts/test_mcp_build_contract.py`. All paths are relative to this repository. `mcp-images-ghcr` publishes `ghcr.io/jtrtdhrst/harness-<service>:sha-<SHA>`; `owned-runtime-images-ghcr` uses that naming rule for GitHub Ops and Multica; `coolify-mcp-ci` publishes `ghcr.io/jtrtdhrst/coolify-mcp:sha-<SHA>`.

| Coolify service | UUID | Build context | Dockerfile (inside context) | SHA-bound publisher |
| --- | --- | --- | --- | --- |
| github-ops-mcp | `t09dqe2eppn2eiqmhzlf8xzp` | `mcp/github-mcp` | `Dockerfile` | `owned-runtime-images-ghcr.yml` |
| multica-mcp | `5o4edyfjo0wftfg08mtkknir` | `mcp/multica-mcp` | `Dockerfile` | `owned-runtime-images-ghcr.yml` |
| coolify-mcp | `f7smgdueq8frlex9lfhp9iji` | `mcp/coolify-mcp` | `Dockerfile` | `coolify-mcp-ci.yml` |
| comfy-mcp | `kkhfw0napmeaqewgdirwhc1h` | `mcp/comfy-mcp` | `Dockerfile` | `mcp-images-ghcr.yml` |
| emailens-mcp | `16qnapdkj0qqqmeokepdechk` | `mcp/emailens-mcp` | `Dockerfile` | `mcp-images-ghcr.yml` |
| hindsight-mcp | `aglen8ervlo2lpi30oz8iii9` | `mcp/hindsight-mcp` | `Dockerfile` | `mcp-images-ghcr.yml` |
| mantic-mcp | `bioufw4uxwuhmr51ueyahf0u` | `mcp/mantic-mcp` | `Dockerfile.http` | `mcp-images-ghcr.yml` |
| opik-mcp | `egasedqaofxnzcqppuxi805h` | `mcp/opik-mcp` | `backend/Dockerfile` | `mcp-images-ghcr.yml` |
| plasmic-mcp | `a6ci2beifbinzckfnneiqnjd` | `mcp/plasmic-mcp` | `Dockerfile` | `mcp-images-ghcr.yml` |
| playwright-mcp | `9e4fzsodixl4qzzap4zg0ntp` | `mcp/playwright-mcp` | `Dockerfile` | `mcp-images-ghcr.yml` |
| supabase-mcp | `tjit4c8m0kjh8brkmdhyvkde` | `mcp/supabase-mcp` | `Dockerfile` | `mcp-images-ghcr.yml` |
| ubuntu-mcp | `lcnjb3vreec7saihkhan6akh` | `mcp/ubuntu-mcp` | `Dockerfile` | `mcp-images-ghcr.yml` |

Additional owned non-MCP runtime image roots (Hermes Gateway and RepoWise deployment publisher staging) use `owned-runtime-images-ghcr.yml`; this table excludes them because their service identifiers are not MCPs.

- Retired `qdrant-mcp` (source retirement merged as PR #182): `mcp/qdrant-mcp` and its MCP image build selection were removed from `main`; the separate `qdrant` database is preserved. Do not treat the exited legacy MCP service as a source-owned build target or revive its deployment.

## Exceptions, not evidence of source ownership

- `cloudflared-mcp` and `mcp-activation`: vendor-image network/activation services, **not** a compiled MCP source checkout. If custom implementation is introduced, it must first be committed in an owned root and added to the source catalog and guarded publisher.
- `repowise-mcp-runtime`: recorded as `local-image-unknown-source`, **not compliant yet**. Do not pretend an image-only service is source-owned or create an empty placeholder folder. Resolve source provenance via its existing RepoWise source/release work and independent review before declaring it part of the owned-build set.
- `zar-i-szlif-mcp-host` and `zar-i-szlif-mcp-host-image`: **other repository** `jtrtdhrst/zar-i-szlif`. Validate/build them under their owning repo's own CI; do not copy product code into Harness.

## Verification commands and ownership boundaries

```sh
python3 -m unittest discover -s scripts -p 'test_mcp_build_contract.py' -v
python3 -m unittest discover -s scripts -p 'test_select_mcp_builds.py' -v
python3 -m unittest discover -s scripts -p 'test_select_owned_runtime_builds.py' -v
python3 -m unittest discover -s scripts -p 'test_service_build_roots.py' -v
```

`source-build-roots-pr.yml` validates declared real Docker contexts at PR SHA. Publishing workflows run only from trusted `main`; **no publishing workflow is allowed to bypass an independent release gate**. For runtime truth inspect Coolify UUID, exact running container image, OCI digest, revision label and authenticated MCP positive/negative E2E; update evidence separately and only from actual observations.

Indexing: `ops/repowise/repowise_github_sync.sh` is the existing GitHub-to-RepoWise ingest path. After merging this document to `main`, sync, verify `indexed_commit == live_head == GitHub main`, and query this exact document; until then it is a PR proposal and not indexed authoritative truth.
