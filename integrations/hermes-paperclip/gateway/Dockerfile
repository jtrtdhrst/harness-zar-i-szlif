# Pinned Hermes production image; source drift fails the build.
FROM nousresearch/hermes-agent:v0.22.5

USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*

COPY run_mcp.py /opt/hermes/gateway/run_mcp.py
COPY install_run_mcp.py /tmp/install_run_mcp.py
RUN python3 /tmp/install_run_mcp.py \
    && python3 -m py_compile /opt/hermes/gateway/run_mcp.py /opt/hermes/gateway/platforms/api_server_runs.py \
    && rm -f /tmp/install_run_mcp.py

CMD ["gateway", "run"]
