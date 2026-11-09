# RepoWise workspace conformance — native policy snapshot (2026-11-09)

This note versions the **native RepoWise** configuration applied to the production RepoWise *knowledge workspace*, not the product backend. The executable configuration is in the persistent `/workspace/.repowise-workspace.yaml` of the RepoWise application container. Preserve both repo entries and indexed commit metadata; apply only the `conformance.rules` section below.

```yaml
conformance:
  rules:
    - source: product
      target: harness::paperclip-mcp
      description: Product runtime must not depend on legacy Paperclip control plane
    - source: product
      target: harness::multica-mcp
      description: Product runtime must not depend on agent orchestration MCP
```

The authoritative syntax is RepoWise v0.60.1 `WorkspaceConfig.conformance.rules`, not a custom policy engine. Existing workspace data was backed up before the change to `/opt/repowise-knowledge/rollback/repowise-workspace-before-conformance-20261109.yaml`.

Native execution and verification:

```text
repowise update --workspace --index-only
repowise workspace check --format json
RepoWise MCP get_conformance
```

Readback: `rules_evaluated=2`, `violation_count=0`, `total_cycles=0`. An isolated negative test using the **installed RepoWise** `check_conformance` library and an existing source-graph edge proved that a matching deny rule produces exactly one violation; this test did not modify live policy.

**Important limitation:** the source graph has 14 detected services but 9 isolated service nodes, with generic-path matches and unresolved consumers. No allow rules were created for questionable dependencies. Never call 0 violations proof of end-to-end topology, and do not infer runtime reachability from a route-only match. Review matching provider/consumer implementations, host identity and deployed image before making any additional manual links or policy assertions.

No LLM provider or embedding configuration was changed. The user manages these separately.
