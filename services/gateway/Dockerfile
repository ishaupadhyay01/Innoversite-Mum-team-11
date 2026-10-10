# syntax=docker/dockerfile:1
# Build context: repository root (see docker-compose.yml)

# Swagger UI assets are vendored at build time so /api/docs works without internet access at runtime.
FROM node:20-alpine AS swagger
RUN npm install --prefix /tmp/sw swagger-ui-dist@5.18.2 --no-audit --no-fund

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN useradd --create-home --uid 10001 iris

COPY services/gateway/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY shared /shared
RUN pip install /shared

COPY services/gateway/app ./app
COPY --from=swagger /tmp/sw/node_modules/swagger-ui-dist/swagger-ui-bundle.js \
                    /tmp/sw/node_modules/swagger-ui-dist/swagger-ui.css \
                    /tmp/sw/node_modules/swagger-ui-dist/favicon-32x32.png \
                    ./app/static/swagger/

USER iris
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
