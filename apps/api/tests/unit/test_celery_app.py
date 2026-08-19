"""Guards against the exact bug found while manually running a live
worker: `autodiscover_tasks`' default `related_name="tasks"` finds
nothing when the task module is `jobs/indexing.py`, and fails *silently*
— no error, just an empty task registry, so every connector-connect
indexing job vanishes into the queue with nothing to run it. This test
would have caught that without needing to start a real worker."""

from relay_api.jobs.celery_app import celery_app


def test_index_connector_task_is_registered() -> None:
    assert "relay_api.jobs.indexing.index_connector_task" in celery_app.tasks


def test_resync_all_connectors_task_is_registered() -> None:
    assert "relay_api.jobs.indexing.resync_all_connectors_task" in celery_app.tasks


def test_beat_schedule_fires_the_resync_task() -> None:
    # Guards the equivalent silent-failure mode for Beat: a typo'd task
    # name here means the schedule fires into the void, same as the
    # autodiscover bug above but for the periodic sweep specifically.
    entry = celery_app.conf.beat_schedule["resync-all-connectors"]
    assert entry["task"] == "relay_api.jobs.indexing.resync_all_connectors_task"
