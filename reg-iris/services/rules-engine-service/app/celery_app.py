from celery import Celery

from app.config import get_settings
from iris_common.events import TASK_ROUTES

settings = get_settings()

celery_app = Celery("rules", broker=settings.redis_url, backend=settings.redis_url, include=["app.tasks"])
celery_app.conf.update(
    task_routes=TASK_ROUTES,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_always_eager=settings.celery_task_always_eager,
    result_expires=3600,
)
