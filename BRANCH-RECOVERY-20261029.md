# Legacy branch recovery — 2026-10-29

Recovered code is **quarantined** under the appropriate service's `_recovered/<source-branch>/` directory. These files are complete snapshots of selected changed files as they existed on the historical branches in `miloszspyrka-code/zar-i-szlif`. They are NOT merged into the live service source or deployed.

Recovered independent MCP / infra branches:
- `KOMAA-1479`: Paperclip OAuth origin and edge identity
- `KOMAA-1469`: Qdrant cutover documentation
- `fix/mcp-deployment-truth-20261024`: Paperclip deployment truth
- `fix/paperclip-ci-failclosed-20261023`: fail-closed Git checks
- `KOMAA-1458`: Paperclip reconciliation, recreate policy, supervisor
- `KOMAA-1008/mcp-worker-edge`: edge worker changes
- `fix/plasmic-workflow-checkout-ref`: Plasmic sync workflow
- `ops/plasmic-build-cache`: Plasmic cache
- `KOMAA-1174`: design-stack/Plasmic MCP changes (marketing content belongs to product archive)

Original branch SHAs and remaining branch ownership must be audited before any branch deletion. The active service folders must be updated via an explicit diff, tests and production readback before replacing any of the versions recovered here. Do not enable recovered GitHub Actions or supervisor scripts implicitly.

Additional independent infrastructure source recovered (not enabled): `KOMAA-411`, `KOMAA-841-fail-closed-execution-truth`, `KOMAA-879`, `KOMAA-1084`, `cutover/qdrant-mcp-upstream-edge-20261027`, `fix/plasmic-publish-checkout-20261022`, `ops/docker-to-coolify-20261028`. Service-specific files remain in their respective `_recovered/` folders; cross-service scripts/docs are in `recovered-branches/`.
