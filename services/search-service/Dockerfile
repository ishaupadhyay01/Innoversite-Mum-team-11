# syntax=docker/dockerfile:1
# Build context: repository root (see docker-compose.yml)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN useradd --create-home --uid 10001 iris \
 && mkdir -p /data/uploads \
 && chown -R iris:iris /data

COPY services/search-service/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY shared /shared
RUN pip install /shared

COPY services/search-service/app ./app

USER iris
EXPOSE 8002
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=12 \
  CMD python -c "import json,urllib.request,sys; d=json.load(urllib.request.urlopen('http://127.0.0.1:8002/health',timeout=4)); sys.exit(0 if d.get('status')=='ok' else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--proxy-headers"]
