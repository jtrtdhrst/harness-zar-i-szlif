# Hermes Gateway base image deployed in Coolify.
# Install the HTTP probe binary used by Coolify's generated Docker healthcheck.
# Coolify must check dashboard port 9119: GET /api/status -> 200.
# Dashboard readiness alone is not agent execution E2E readiness.
FROM nousresearch/hermes-agent:v0.22.5

USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*

CMD ["gateway", "run"]
