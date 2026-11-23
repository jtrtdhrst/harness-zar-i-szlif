"""Fail-closed canonical source-prefix ownership for Harness release admission.

A service may only attest/deploy changes from its explicitly owned source root.
The mapping is static and reviewed with source; it MUST NOT be derived from a
mutable Coolify request, environment variable, agent string or PR payload.
"""
from __future__ import annotations

MCP_SERVICES = frozenset({
    "comfy-mcp","coolify-mcp","emailens-mcp","hindsight-mcp",
    "mantic-mcp","multica-mcp","opik-mcp","plasmic-mcp",
    "playwright-mcp","qdrant-mcp","supabase-mcp","ubuntu-mcp"
})
OTHER_ROOTS = {
    "github-ops-mcp": "mcp/github-mcp",
    "mcp-edge": "gateways/mcp-edge",
    "plasmic": "apps/plasmic",
    "opik-run-enricher": "workers/opik-run-enricher",
    "hermes-gateway": "integrations/hermes-paperclip/gateway",
    "repowise-deployment-publisher-staging": "ops/repowise",
}

def source_path_prefix(service: str) -> str:
    if not isinstance(service, str) or not service or "/" in service or service.startswith("."):
        raise ValueError("invalid_source_service")
    if service in MCP_SERVICES:
        return "mcp/" + service + "/"
    return OTHER_ROOTS.get(service, service) + "/"
