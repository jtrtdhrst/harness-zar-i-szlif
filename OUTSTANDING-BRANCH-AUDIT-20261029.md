# Outstanding 19 branch comparison audit — 2026-10-29

Compared source `miloszspyrka-code/zar-i-szlif` branches against its cleaned `main`. Compare file lists reflect aggregate history and are **not** proof that code is missing from target repos. These are read-only observations.

## No ahead commits (6)
`KOMAA-1415`, `KOMAA-1442`, `KOMAA-1459`, `KOMAA-1463`, `KOMAA-1464`, `deploy/plasmic-selfhost-20261025`.

## Ahead commits: preserve and validate (13)
| Branch | Ahead | Changed paths returned | Classification to investigate |
|---|---:|---:|---|
| `KOMAA-1094` | 22 | 300 (compare truncated) | mascot assets/design |
| `KOMAA-1146` | 15 | 68 | mascot assets, CI |
| `brand/zar-i-szlif-direct-20261013` | 22 | 17 | shared docs, product brand |
| `chore/current-context-docs-20261021` | 4 | 15 | docs/archive |
| `chore/monorepo-mcp-segmentation-20261022` | 20 | 233 | infrastructure + product |
| `ci/website-branch-gate-20261023` | 25 | 39 | website/CI |
| `design/mascot-minimal-flat-v3-20261020` | 9 | 7 | mascot assets |
| `feat/mcp-nine-worker-roots-20261022` | 35 | 300 (compare truncated) | MCP services |
| `fix/panel-release-ci-gate-20261028` | 2 | 1 | CI |
| `fix/zar-i-szlif-canonical-brand-20261013` | 2 | 18 | brand/product |
| `mascots-v7-design-preview` | 24 | 300 (compare truncated) | mascot assets |
| `plasmic/website` | 6 | 6 | website |
| `release/panel-stable-20261027` | 1 | 1 | CI |

## Next verification
1. For each branch with ahead commits, inspect its changed files **against target repo trees**, including binary assets, and preserve unique content under correct service/product archive ownership. Note: compare API responses cap output at 300 paths.
2. Preserve branch heads and commit provenance; run package tests where code is activated.
3. GitHub connector exposes no delete-ref/delete-branch operation. Branch deletion must be performed by an authorized git/GitHub execution environment after validating preservation.
4. Confirm Coolify/Cloudflare integration endpoints and live deployments separately; no cutover was performed.

No source branch was deleted by this audit.
