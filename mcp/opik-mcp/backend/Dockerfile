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
COPY backend/LICENSE /app/LICENSE
RUN useradd --uid 10001 --create-home app
USER 10001
EXPOSE 8080
ENTRYPOINT ["python", "-m", "opik_mcp"]
