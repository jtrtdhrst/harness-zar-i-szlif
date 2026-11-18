FROM python:3.12-slim
ARG REPOWISE_VERSION=0.60.1
ENV PYTHONUNBUFFERED=1 DO_NOT_TRACK=1 REPOWISE_TELEMETRY_DISABLED=1
RUN apt-get update && apt-get install -y --no-install-recommends git libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir "repowise==${REPOWISE_VERSION}"
RUN groupadd -r repowise && useradd -r -g repowise -m -d /home/repowise -s /usr/sbin/nologin repowise \
    && mkdir -p /workspace /home/repowise/codex-state && chown -R repowise:repowise /workspace /home/repowise
USER repowise
WORKDIR /workspace
EXPOSE 7338
ENTRYPOINT ["repowise", "mcp"]
CMD ["/workspace", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "7338", "--tools", "get_answer,get_context,get_symbol,search_codebase,get_risk,get_change_risk,get_why,get_overview,get_health,get_dead_code,list_repos,get_dependency_path,get_execution_flows,get_blast_radius,get_architecture,get_conformance"]
