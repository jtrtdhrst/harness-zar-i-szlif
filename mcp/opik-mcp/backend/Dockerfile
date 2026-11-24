FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
# Coolify's configured HTTP healthcheck invokes curl inside the container.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.lock /app/requirements.lock
RUN python -m pip install --no-cache-dir -r /app/requirements.lock
COPY backend/source-parts/ /app/source-parts/
RUN python -c 'import pathlib,tarfile,hashlib,io; root=pathlib.Path("/app/source-parts"); payload=b"".join(p.read_bytes() for p in sorted(root.glob("part-*"))); wanted=(root/"ARCHIVE.sha256").read_text().strip(); assert hashlib.sha256(payload).hexdigest()==wanted, "opik_runtime_source_digest_mismatch"; t=tarfile.open(fileobj=io.BytesIO(payload),mode="r:xz"); t.extractall("/app",filter="data"); t.close()' \
 && rm -rf /app/source-parts
COPY backend/patch_score_batch.py /app/patch_score_batch.py
RUN python /app/patch_score_batch.py /app/opik_mcp/writes/operations/observability.py
COPY backend/execution_summary.py /app/opik_mcp/server/tools/execution_summary.py
RUN python -c 'import hashlib,pathlib; p=pathlib.Path("/app/opik_mcp/server/tools/__init__.py"); s=p.read_bytes(); assert hashlib.sha256(s).hexdigest()=="cb85681240e3ce02a8459c98be25bc6b76b9727aa94e5e9457033d3418cab710", "unexpected_tool_registry"; a=b"    extend_advertised_schemas(mcp, toggles)"; assert s.count(a)==1; p.write_bytes(s.replace(a,b"    from opik_mcp.server.tools import execution_summary\\n    execution_summary.register(mcp)\\n"+a)); compile(p.read_bytes(),str(p),"exec")' \
 && python /app/opik_mcp/server/tools/execution_summary.py
COPY backend/LICENSE /app/LICENSE
RUN useradd --uid 10001 --create-home app
USER 10001
EXPOSE 8080
ENTRYPOINT ["python", "-m", "opik_mcp"]
