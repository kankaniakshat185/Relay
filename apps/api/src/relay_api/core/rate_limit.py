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

_SECONDS_PER_DAY_WITH_BUFFER = 60 * 60 * 26  # a little past midnight UTC, for clock skew

_client: redis.Redis[str] | None = None


def _redis() -> redis.Redis[str]:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, decode_responses=True)
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
