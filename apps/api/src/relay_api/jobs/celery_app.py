from celery import Celery

from relay_api.core.config import get_settings

settings = get_settings()

celery_app = Celery("relay", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# related_name="indexing", not the default "tasks" — our task module is
# jobs/indexing.py, not jobs/tasks.py. Without this, autodiscover silently
# finds nothing (confirmed by an empty [tasks] list at worker startup) and
# every connector-connect indexing job would just vanish into the queue
# with no worker registered to run it.
celery_app.autodiscover_tasks(["relay_api.jobs"], related_name="indexing")
