"""Exercises the actual Redis INCR/EXPIRE behavior — not mocked, since the
whole point is verifying the counter really persists and really caps."""

import uuid

from relay_api.core.rate_limit import check_and_increment_daily


async def test_allows_calls_under_the_limit() -> None:
    key = f"test:{uuid.uuid4()}"

    assert await check_and_increment_daily(key, limit=3) is True
    assert await check_and_increment_daily(key, limit=3) is True
    assert await check_and_increment_daily(key, limit=3) is True


async def test_rejects_calls_once_the_limit_is_reached() -> None:
    key = f"test:{uuid.uuid4()}"

    for _ in range(5):
        await check_and_increment_daily(key, limit=5)

    assert await check_and_increment_daily(key, limit=5) is False


async def test_different_keys_have_independent_counters() -> None:
    key_a, key_b = f"test:{uuid.uuid4()}", f"test:{uuid.uuid4()}"

    await check_and_increment_daily(key_a, limit=1)
    assert await check_and_increment_daily(key_a, limit=1) is False

    assert await check_and_increment_daily(key_b, limit=1) is True
