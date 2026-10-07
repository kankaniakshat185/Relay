"""A small Redis-backed daily counter — currently used for exactly one
thing: capping free-tier (server-key) LLM synthesis calls per user per
day (ADR 0008). BYOK requests never touch this.

Not a general-purpose rate-limiting framework — if a second use case
shows up, that's the point to generalize this, not before.
"""

# redis.Redis is only generic in the type stubs, not at runtime — deferred
# annotation evaluation (PEP 563) keeps `redis.Redis[str]` below from being
# evaluated as a real subscript at import time.
from __future__ import annotations

from datetime import UTC, datetime

import redis.asyncio as redis

from relay_api.core.config import get_settings
from relay_api.core.redis_tls import sanitized_redis_url, tls_config_if_needed

_SECONDS_PER_DAY_WITH_BUFFER = 60 * 60 * 26  # a little past midnight UTC, for clock skew

_client: redis.Redis[str] | None = None


def _redis() -> redis.Redis[str]:
    """Found live: every call raised `RedisError: Invalid SSL Certificate
    Requirements Flag: CERT_NONE` in production, the first time this
    client actually issued a command (`INCR`), while Celery's own broker
    connection — same `REDIS_URL` — worked fine. Root cause: the
    production `REDIS_URL`'s querystring carries `ssl_cert_reqs=CERT_NONE`
    (the Python enum's *name*; redis-py only accepts the lowercase
    `"none"`/`"optional"`/`"required"` there), and per redis-py's own
    `from_url` docs, a querystring value always overrides an explicit
    keyword argument — so passing `ssl_cert_reqs=ssl.CERT_NONE` here
    wouldn't have been enough on its own (confirmed locally before
    writing this fix). `sanitized_redis_url` strips that querystring
    value; `tls_config_if_needed` then supplies the correct one as an
    explicit kwarg, the same pairing `jobs/celery_app.py` needed for its
    own, independent Redis connection — see `core/redis_tls.py`."""
    global _client
    if _client is None:
        url = get_settings().redis_url
        tls_kwargs = tls_config_if_needed(url) or {}
        _client = redis.from_url(sanitized_redis_url(url), decode_responses=True, **tls_kwargs)
    return _client


async def check_and_increment_daily(key: str, limit: int) -> bool:
    """Increments today's counter for `key` and returns whether the caller
    is still under `limit` (i.e. whether this call is allowed). The
    increment happens regardless — a request that gets rejected still
    counts as an attempt, so this can't be bypassed by retrying."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    redis_key = f"ratelimit:{key}:{today}"

    client = _redis()
    count = await client.incr(redis_key)
    if count == 1:
        await client.expire(redis_key, _SECONDS_PER_DAY_WITH_BUFFER)

    return count <= limit
