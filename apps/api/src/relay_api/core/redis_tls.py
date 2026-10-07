"""Shared TLS handling for every direct Redis client this process creates
— originally lived only in `jobs/celery_app.py`, moved here once a second,
independent Redis client (`core/rate_limit.py`'s free-tier counter) hit
the exact same class of bug Celery's broker connection already had a fix
for. See `rate_limit.py`'s own docstring for that second occurrence.
"""

import ssl
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


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


def sanitized_redis_url(redis_url: str) -> str:
    """Strips any `ssl_cert_reqs` query parameter from `redis_url`.

    Found live: the raw `redis://`/`rediss://` client (`redis.asyncio`, used
    directly by `core/rate_limit.py`, unlike Celery/kombu's own transport)
    reads `ssl_cert_reqs` out of the URL's own querystring, and — per
    `redis.asyncio.connection.parse_url`'s own docstring — "in case of
    conflicting arguments, querystring arguments always win," overriding
    any `ssl_cert_reqs` passed as an explicit keyword argument to
    `from_url`. The production `REDIS_URL` carries `ssl_cert_reqs=CERT_NONE`
    (the Python enum's *name*) in its querystring; redis-py only accepts
    the lowercase strings `"none"`/`"optional"`/`"required"` there, so every
    real command raised `RedisError: Invalid SSL Certificate Requirements
    Flag: CERT_NONE` the first time it tried to actually connect — reproduced
    locally (see `tests/unit/core/test_redis_tls.py`) by passing
    `ssl_cert_reqs=ssl.CERT_NONE` explicitly to `from_url` *and* confirming
    it still crashed, because the broken querystring value wins regardless.
    Stripping the querystring value here and setting `ssl_cert_reqs`
    explicitly via `tls_config_if_needed` above is the only combination that
    actually works — passing the kwarg alone is not enough."""
    parts = urlsplit(redis_url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "ssl_cert_reqs"]
    return urlunsplit(parts._replace(query=urlencode(query)))
