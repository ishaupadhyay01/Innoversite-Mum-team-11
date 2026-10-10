# Build context: repository root  (docker build -f services/ingestion-service/Dockerfile .)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv

RUN useradd --create-home --uid 10001 iris

COPY services/ingestion-service/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY libs/iris-common /tmp/iris-common
RUN pip install /tmp/iris-common && rm -rf /tmp/iris-common

COPY services/ingestion-service/ ./
RUN chmod +x scripts/entrypoint.sh && mkdir -p /data/regulations && chown -R iris:iris /data /srv
USER iris

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8000/health/live', timeout=2)" || exit 1
ENTRYPOINT ["scripts/entrypoint.sh"]
CMD ["api"]
