# Product and Harness — single workspace, separate owners

| Domain | Repository owner | Verify against |
| --- | --- | --- |
| Product UI, onboarding, patrols, fundraising, app DB and product MCP | `product` | Repo source, actual product release SHA, schema and Worker config |
| Independent MCP services, Hermes, Hindsight, Opik and CI/deployment controllers | `harness` | Service source, Coolify deployment, agent runtime |
| Shared API/provider-consumer contracts | `product` + `harness` | Code signatures, endpoint hosts, tests, actual runtime connections |
| Agent orchestration, prompts, source-provider and memory integrations | `harness` | Current Multica/Hermes configuration, not archived Paperclip instructions |

For every new task: Repowise `list_repos` → exact repository and SHA → `get_context` for affected files → cross-repo `get_blast_radius` → verify candidate edges against implementation and deployment → document tests/review/rollout/readback. 

**Provenance**: Paperclip Wiki historical source is preserved but is NOT a real-time topology, and archived AGENTS.md is not current runtime policy.

Keep original repo code and harness outside this documentation migration.
