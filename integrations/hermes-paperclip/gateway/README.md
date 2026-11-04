# Hermes Gateway image

This is the single source-controlled production Dockerfile for the Hermes Gateway integration.

## Coolify source contract

- Repository: `miloszspyrka-code/harness-zar-i-szlif`
- Branch: `main`, after independent review
- Build context: `/integrations/hermes-paperclip/gateway`
- Dockerfile: `/Dockerfile`
- Watch paths: `integrations/hermes-paperclip/gateway/**`
- Image base: `nousresearch/hermes-agent:v0.22.5`

The image includes GNU Wget for Coolify's in-container HTTP readiness probe. Configure Coolify to probe `GET http://127.0.0.1:8642/health`; dashboard `/api/status` requires dashboard authentication and is not the container readiness endpoint.

Keep profile credentials and the persistent `/opt/data` volume in the existing Coolify runtime configuration. Do not copy them into the image, build logs, or a candidate service.

## Validation and scope

The image workflow builds the final Dockerfile, starts the gateway, verifies the health response, stops the supervised gateway service, and confirms the same probe fails while the service is down.

Passing this image check proves container readiness only. It does not prove Paperclip run-scoped MCP authorization, profile authentication, Hindsight persistence/isolation, or Opik correlation; those remain separate integration gates.


## Paperclip run-scoped adapter documentation

The [canonical integration runbook](../OPERATIONS-STATUS.md) and [candidate receiver contract](RUN_SCOPED_RECEIVER_CANDIDATE.md) are published as documentation only. Candidate source is in [PR #36](https://github.com/miloszspyrka-code/harness-zar-i-szlif/pull/36); do not infer this production Gateway Dockerfile already includes its code. Production acceptance requires native Paperclip review, authorized Wiki/Skills MCP calls, same-run Hindsight/Opik readback and rollback evidence.
