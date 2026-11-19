# Harness and agent infrastructure — observed baseline (2026-11-09)

**Repo:** `miloszspyrka-code/harness-zar-i-szlif`, GitHub `main` SHA: `fe2839d7e41ee3b581f7bf92857a39b1106098f6` (verified on 2026-11-09).

## Service domains (separate lifecycles)

- **Agent control:** Multica and Hermes Gateway; Paperclip remains a legacy runtime and historical Wiki source. Do NOT assume migrated Paperclip role or review configuration is active in Multica.
- **Memory and telemetry:** Hindsight, Qdrant and Opik, with separately deployed components and MCP services. Container `running:healthy` is not proof of agent connectivity.
- **Source and release:** GitHub private repositories; Coolify deployments; Cloudflare edge/proxy and Workers. Repo HEAD != deployed image without digest/readback evidence.
- **Knowledge graph:** one Repowise workspace covering `product` + `harness`, with a private Streamable HTTP MCP server. It indexes code, Git history and historical documents separately. Cross-repo inferred links are candidate evidence, not runtime truth.
- **Product:** see [product repository](https://github.com/miloszspyrka-code/zar-i-szlif) and its current-runtime document for customer-facing app ownership.

## Verified operational probes (2026-11-09)

| Probe | Observed |
| --- | --- |
| Product `https://panel.zariszlif.pl/healthz` | HTTP 200, `ok` |
| Product `https://panel.zariszlif.pl/__release.json` | HTTP 200, `98cd058155dbf4c268777246fc510324f98f7dc5` |
| Multica `https://multica.zariszlif.pl/` | HTTP 200 HTML. Authenticated agent E2E not implied |
| Multica MCP `https://mcp-multifca.zariszlif.pl/health` | HTTP 200, 184 catalog operations; 157 tools; 401 without token; authenticated write/readback/delete PASS |
| Old Outline `https://wiki.zariszlif.pl/` | HTTP 502 after service stopped; NOT a usable active knowledge system |
| Repowise API `/health` | HTTP 200 internal |
| Repowise MCP `http://repowise-mcp:7338/mcp` | `initialize`/`tools/list`/`list_repos`/`get_architecture` passed with authorization |
| Repowise MCP no/bad token | HTTP 401 |
| Repowise MCP status | Coolify `running:healthy` |
| Repowise indexed HEADs | Harness `fe2839d7e41ee3b581f7bf92857a39b1106098f6`, Product `98cd058155dbf4c268777246fc510324f98f7dc5` |
| Live agent consumption and automatic Git private sync | NOT E2E VERIFIED at snapshot |

## Coolify inventory

Connector returned 34 projects, 32 service resources and 12 standalone application resources on 2026-11-09. This table reports provider status; values may change and do not prove individual version/digest.

### Services

| Service | Coolify UUID | Provider status |
| --- | --- | --- |
| cloudflared-mcp | 3byzyvjxsycixyzcpxbujzev | running:healthy |
| cloudflared-paperclip | 64wbd6azqgkapue2dn4dru2z | running:healthy |
| comfy | hdn0rl4wznbvaoizna61bbyy | running:healthy |
| comfy-mcp | kkhfw0napmeaqewgdirwhc1h | running:healthy |
| coolify-mcp | f7smgdueq8frlex9lfhp9iji | running:healthy |
| emailens-mcp | 16qnapdkj0qqqmeokepdechk | running:healthy |
| hermes-paperclip-sync-checks | 4dzjmxkrlqirn07pshmd2b51 | running:healthy |
| hermes-permissions-repair-temporary | 6lyy9zivm73cztvzeiabvmwx | exited |
| hindsight-core | hjda7ckq5z4luhd1vpdepi0r | running:healthy |
| hindsight-mcp | aglen8ervlo2lpi30oz8iii9 | running:healthy |
| mantic-mcp | bioufw4uxwuhmr51ueyahf0u | running:healthy |
| mautic | 8byf8qjxdixpwp7lsnr8zpto | running:healthy |
| mcp-activation | ra0iy2xs7abgms1r0phx4iqg | running:unknown |
| multica-edge | vwe5lv4bniosxug34uhyf0ag | running:unknown |
| multica-stack | 6ihjnudsifbcvklz5hqxdldc | running:healthy |
| opencode | 26aqp0flyvdinjn6dklxnb1c | running:healthy |
| opik | s7a4rwqbij7w4fxlnauriblo | running:healthy |
| opik-mcp | egasedqaofxnzcqppuxi805h | running:healthy |
| opik-run-enricher | kpop6yiy78vnlqaj9dxcaliy | running:healthy |
| outline-knowledge | g16yynrbdpkab4hnmaoj7vxk | exited |
| paperclip | 2omzqpy8dxgmhuwfbzo7bvvv | running:healthy |
| paperclip-mcp | gevr1m6rdj4t4fbhcjvqv8gg | running:healthy |
| plasmic | mzmlcorgkfgdy44hqfmmtxgw | running:healthy |
| plasmic-mcp | a6ci2beifbinzckfnneiqnjd | running:healthy |
| playwright-mcp | 9e4fzsodixl4qzzap4zg0ntp | running:healthy |
| qdrant | eciprwgeyol4znmdd0dpu3xc | running:healthy |
| qdrant-mcp | a4zgmthjspz8hwvyu6llr8dh | running:healthy |
| repowise-mcp-runtime | lecwi3emh9hjxir7gphmalie | running:healthy |
| supabase | r2gnunvpkqwmuew1tupbf7lx | running:healthy |
| supabase-mcp | tjit4c8m0kjh8brkmdhyvkde | running:healthy |
| ubuntu-mcp | lcnjb3vreec7saihkhan6akh | running:healthy |
| ubuntu-mcp-oauth-proxy | rxaybxjqaslqfog9sfwddlr8 | exited |

### Standalone applications

| Application | Coolify UUID | Provider status | Git repo | Branch |
| --- | --- | --- | --- | --- |
| brutal-e2e-canary | ajzfhryquxuntaew2qb97uil | running:unknown | miloszspyrka-code/zar-i-szlif | poc/brutal-e2e-base-20261107181909 |
| hermes-gateway | 2sganhxhhnioiqh4an9g2f4k | running:healthy | miloszspyrka-code/harness-zar-i-szlif | fix/hermes-runmcp-tool-projection-20261106 |
| hermes-gateway-git-release-candidate | hut52do8jdwumzdnaphtnmfp | running:healthy | miloszspyrka-code/harness-zar-i-szlif | fix/hermes-run-mcp-toolset-20261106 |
| hermes-gateway-poc | qycm1xpcgsemlxt6npyhuvkh | exited:unhealthy | coollabsio/coolify | main |
| hermes-git-build-canary | yh20mb2rurecnmn60t5vfc3s | running:healthy | miloszspyrka-code/harness-zar-i-szlif | fix/hermes-runmcp-authority-20261106 |
| multica-hermes-e2e-localbuild | 9ikauoagijplda4skjdv2zej | exited:unhealthy | miloszspyrka-code/zar-i-szlif | poc/multica-hermes-e2e-20261109-base |
| multica-mcp | 5o4edyfjo0wftfg08mtkknir | running:healthy | miloszspyrka-code/harness-zar-i-szlif | main |
| repowise | oea9obpkhzbgkmipxwqmz2hj | running:unknown | repowise-dev/repowise.git | v0.60.1 |
| repowise-harness-source-temp | mdccyotmyyi7krjqhop8kh7b | exited:unhealthy | miloszspyrka-code/harness-zar-i-szlif | main |
| repowise-mcp | fciqzgceop7mqtqickkfomd7 | exited:unhealthy | repowise-dev/repowise.git | v0.60.1 |
| repowise-product-source-temp | u5pjaspn0wofcjr4yd53pytr | exited:unhealthy | miloszspyrka-code/zar-i-szlif | main |
| zar-i-szlif-web | k0vwdsjazxguvgmh4qixjgxn | running:healthy | miloszspyrka-code/zar-i-szlif | ci-approved |

## Cross-repo analysis caveat

Repowise first detected 10 system nodes and 3 edges. Some matched only `GET /health` or OAuth discovery routes, which are generic and cannot establish real dependencies. Therefore **architecture evidence is partial**, and the graph MUST NOT be used as a sole release gate until verified by actual code and runtime config.

## Paperclip Wiki migration and governance

Original 108 pages are preserved under one of the two repository-specific `docs/knowledge/paperclip-archive` trees with byte-identical checksums and a migration manifest. Archive content is **historical**: agent role instructions, permissions and review policies from Paperclip do not automatically apply to Multica or Hermes.

### Release evidence standard

- exact source SHA/PR and independent review where currently required
- reproducible targeted tests and permissions preflight
- immutable image digest / deployment UUID
- environment configuration identity (names, no secret values)
- live authenticated tool/HTTP readback and rollback/forward evidence
- source-checked documentation disposition

**Never equate** an indexed repo, successful build or Coolify `healthy` flag with an end-to-end product release.

*This file describes observations as of 2026-11-09, not a continuously verified status board.*
