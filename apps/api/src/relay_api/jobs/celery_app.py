import ssl

from celery import Celery
from celery.schedules import crontab

# Must run before anything in this process touches the database — see
# that module's own docstring. Found live: `index_connector_task`'s
# `db.commit()` raised `NoReferencedTableError` on `users` the first time
# it actually ran in production, because this process never otherwise
# imports `auth.models` (only `main.py`'s router chain does).
from relay_api.core import model_registry  # noqa: F401
from relay_api.core.config import get_settings

settings = get_settings()

celery_app = Celery("relay", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Every call site uses `.delay()` and never reads a result back
    # (`connectors/router.py`, `jobs/indexing.py`, `jobs/flaky_tests.py` —
    # all fire-and-forget). Without this, Celery still writes each task's
    # state/result to the Redis backend anyway, on every single run of the
    # 15-minute periodic resync — pure wasted Redis requests against
    # Upstash's free-tier monthly cap (found live: exhausted the 500,000-
    # request limit running continuously for about a week, seemingly from
    # this kind of steady background traffic more than actual task
    # volume). This doesn't fix the cap itself, just stops paying for
    # writes nothing ever reads.
    task_ignore_result=True,
)


def tls_config_if_needed(redis_url: str) -> dict[str, int] | None:
    """Upstash's managed Redis (used in production) issues `rediss://` URLs
    (TLS) — Celery/kombu's redis transport refuses to even connect over
    `rediss://` without an explicit `ssl_cert_reqs`, raising `ValueError: A
    rediss:// URL must have parameter ssl_cert_reqs...` the first time
    anything actually tries to publish or consume. Found live: every
    `.delay()` call (the OAuth callback's post-connect indexing kickoff,
    and the manual "Sync Now" endpoint) hit this and raised uncaught,
    surfacing as a raw 500 — for the OAuth callback specifically, *after*
    the connector credential had already been committed to the database,
    which is why refreshing the page afterward showed it connected anyway.

    `CERT_NONE`, not `CERT_REQUIRED`: this only authenticates the Redis
    transport, which is already authenticated by the URL's own password;
    verifying Upstash's cert chain would need extra CA bundle setup this
    app doesn't otherwise need. Returns `None` for a plain `redis://` URL
    (local dev, `docker run redis:7-alpine`) — no TLS config to add."""
    if not redis_url.startswith("rediss://"):
        return None
    return {"ssl_cert_reqs": ssl.CERT_NONE}


_tls_config = tls_config_if_needed(settings.redis_url)
if _tls_config is not None:
    celery_app.conf.broker_use_ssl = _tls_config
    celery_app.conf.redis_backend_use_ssl = _tls_config

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
