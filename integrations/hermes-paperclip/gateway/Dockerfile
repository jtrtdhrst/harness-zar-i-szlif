# Hermes Gateway base image deployed in Coolify.
# Install GNU Wget for Coolify's source-configured HTTP readiness probe.
# Use the gateway API endpoint GET http://127.0.0.1:8642/health; it does not require dashboard auth setup.
# Gateway readiness alone is not Paperclip agent execution E2E readiness.
FROM nousresearch/hermes-agent:v0.22.5

USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*

CMD ["gateway", "run"]
