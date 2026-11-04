FROM python:3.13-alpine
WORKDIR /app
COPY worker.py /app/worker.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 1000:1000
CMD ["python", "/app/worker.py"]
