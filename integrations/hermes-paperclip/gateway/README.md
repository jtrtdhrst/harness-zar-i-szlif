# Hermes Gateway image

This is the single source-controlled production Dockerfile for the Hermes Gateway integration.

## Coolify source contract

- Repository: `miloszspyrka-code/harness-zar-i-szlif`
- Branch: `main`, after independent review
- Build context: `/integrations/hermes-paperclip/gateway`
- Dockerfile: `/Dockerfile`
- Watch paths: `integrations/hermes-paperclip/gateway/**`
- Image base: `nousresearch/hermes-agent:v0.22.5`
- Hermes source pin: `NousResearch/hermes-agent@bf0203a794a07aac3ff764972ab9087baa4e4f4e`

The image includes GNU Wget for Coolify's in-container HTTP readiness probe. Configure Coolify to probe `GET http://127.0.0.1:8642/health`; dashboard `/api/status` requires dashboard authentication and is not the container readiness endpoint.

Keep profile credentials and the persistent `/opt/data` volume in the existing Coolify runtime configuration. Do not copy them into the image, build logs, or a candidate service.

## Validation and scope

The image workflow builds the final Dockerfile, starts the gateway, verifies the health response, stops the supervised gateway service, and confirms the same probe fails while the service is down.

Passing this image check proves container readiness only. It does not prove Paperclip run-scoped MCP authorization, profile authentication, Hindsight persistence/isolation, or Opik correlation; those remain separate integration gates.

## Run-scoped MCP receiver work

`run_mcp.py` defines the strict grant envelope and a context manager over Hermes' existing
`gateway.session_local_mcp._borrowed` facility. The grant is accepted only on a profile-authenticated
request; the opaque bearer is retained only in the in-memory server spec and the upstream MCP
gateway must validate it on every tool call. The run id is the scope namespace, so connections
cannot be reused across runs. Never persist this envelope, include it in prompts, or log request
bodies.

This helper is not wired into the pinned `/v1/runs` executor yet. The API currently admits a
`_RunLaunch` and invokes `_run_agent_sync` without a runtime-MCP argument or a Hermes execution
authority in scope. Therefore this commit is a tested receiver component, **not** a functioning
Paperclip-to-Hermes bridge and must not be deployed or treated as acceptance. The integration hook
must be added to the version-pinned `gateway/platforms/api_server_runs.py` path, with cleanup on
success, error, and cancellation, before the feature can be considered ready.
