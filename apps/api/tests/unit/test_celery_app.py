"""Guards against the exact bug found while manually running a live
worker: `autodiscover_tasks`' default `related_name="tasks"` finds
nothing when the task module is `jobs/indexing.py`, and fails *silently*
— no error, just an empty task registry, so every connector-connect
indexing job vanishes into the queue with nothing to run it. This test
would have caught that without needing to start a real worker."""

from relay_api.jobs.celery_app import celery_app


def test_index_connector_task_is_registered() -> None:
    assert "relay_api.jobs.indexing.index_connector_task" in celery_app.tasks
