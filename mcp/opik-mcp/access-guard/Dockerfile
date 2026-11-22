FROM python:3.12-slim
RUN pip install --no-cache-dir PyJWT==2.10.1 cryptography==46.0.5 \
 && useradd --no-create-home --uid 10001 --shell /usr/sbin/nologin guard
WORKDIR /app
COPY --chown=10001:10001 guard.py /app/guard.py
USER 10001
EXPOSE 8088
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/healthz',timeout=3)"
CMD ["python","-u","/app/guard.py"]
