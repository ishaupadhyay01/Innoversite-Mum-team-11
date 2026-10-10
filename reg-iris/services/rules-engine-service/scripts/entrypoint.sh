#!/bin/sh
# Usage: entrypoint.sh api|worker|migrate
set -e
case "${1:-api}" in
  api)
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
    ;;
  worker)
    exec celery -A app.celery_app:celery_app worker -Q rules -n rules@%h \
      --loglevel "${LOG_LEVEL:-INFO}" --concurrency "${WORKER_CONCURRENCY:-2}"
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  *)
    exec "$@"
    ;;
esac
