from celery import Celery
from celery.schedules import crontab

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

# Same reasoning, second task module: jobs/flaky_tests.py won't be found
# unless it's named explicitly too — `related_name` only matches one
# module name per call. Two `autodiscover_tasks` calls each register
# their own `on_after_finalize` hook (Celery supports multiple), not one
# overwriting the other — confirmed live, not just assumed, given this
# exact class of bug (a task silently never registering) already bit this
# app once (see jobs/indexing.py's own comment on the first occurrence).
celery_app.autodiscover_tasks(["relay_api.jobs"], related_name="flaky_tests")

# Indexing otherwise only ever runs once, at connect time (connectors/router.py's
# OAuth callback) — nothing re-syncs GitHub/Slack/Jira activity that happens
# after that. This periodic sweep is the fix, for all three providers at
# once (see jobs/indexing.resync_all_connectors_task). Every 15 minutes:
# frequent enough that new activity shows up in a reasonable window,
# nowhere close to any of the three providers' actual rate limits even
# with many connected accounts. Requires a `celery beat` process running
# alongside the worker — see README for the local command; in production
# this is a second process (or `celery worker -B` combining both, fine at
# small scale, not once there's more than one worker replica).
celery_app.conf.beat_schedule = {
    "resync-all-connectors": {
        "task": "relay_api.jobs.indexing.resync_all_connectors_task",
        "schedule": crontab(minute="*/15"),
    },
    # Separate task, separate schedule entry (not folded into the resync
    # above) — this writes to a completely different table
    # (`flaky_test_workflow_runs`, not `ingested_items`), matching Flaky
    # Test Investigator's "standalone subsystem" scope (see ADR 0018).
    # Same 15-minute cadence — no reason for CI-run freshness to lag
    # everything else's.
    "resync-all-flaky-tests": {
        "task": "relay_api.jobs.flaky_tests.resync_all_flaky_tests_task",
        "schedule": crontab(minute="*/15"),
    },
}
