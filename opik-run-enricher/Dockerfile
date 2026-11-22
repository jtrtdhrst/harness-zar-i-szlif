# Source-controlled, clean-build runtime for Opik trace enrichment.
FROM python:3.13.18-alpine3.24
WORKDIR /app
COPY --chown=1000:1000 worker.py retrieval_evidence.py /app/
USER 1000:1000
CMD ["python", "/app/worker.py"]
