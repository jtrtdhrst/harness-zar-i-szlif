# Pinned Hermes production image; source drift fails the build.
# Base is pinned by tag (readability) AND manifest digest (immutability) so the
# startup path below cannot change under a moved tag.
# v0.22.5 index digest sha256:9c5561579f3ffdf333401797094ac3a743738d6c25d40f4331c7bf77b694238d
# linux/amd64 manifest sha256:fd822bae0a61bf023450737edbeaeea5fc6460f17cb4ee240a7e67b306ed63fb
FROM nousresearch/hermes-agent:v0.22.5@sha256:9c5561579f3ffdf333401797094ac3a743738d6c25d40f4331c7bf77b694238d

USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*

COPY run_mcp.py /opt/hermes/gateway/run_mcp.py
COPY install_run_mcp.py /tmp/install_run_mcp.py
COPY install_plugin_load_wait.py /tmp/install_plugin_load_wait.py
RUN python3 /tmp/install_run_mcp.py \
    && python3 /tmp/install_plugin_load_wait.py \
    && python3 -m py_compile /opt/hermes/gateway/run_mcp.py /opt/hermes/gateway/platforms/api_server_runs.py /opt/hermes/plugins/plugin_loader.py \
    && rm -f /tmp/install_run_mcp.py /tmp/install_plugin_load_wait.py

CMD ["gateway", "run"]
