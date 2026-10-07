"""Guards the production bug: `core/rate_limit.py`'s Redis client must
build from a sanitized URL with an explicit TLS kwarg, not the raw
`settings.redis_url` — see `_redis`'s own docstring and
`core/redis_tls.py` for the full story. Mocks `redis.asyncio.from_url`
so this runs with no real Redis connection, the same way
`tests/unit/core/test_redis_tls.py` tests the two helpers directly."""

import ssl
from unittest.mock import patch

import relay_api.core.rate_limit as rate_limit_module


def test_redis_client_strips_broken_querystring_and_sets_tls_kwarg() -> None:
    rate_limit_module._client = None
    url = "rediss://default:pw@example.upstash.io:6379/0?ssl_cert_reqs=CERT_NONE"

    with (
        patch.object(rate_limit_module, "get_settings") as mock_settings,
        patch("redis.asyncio.from_url") as mock_from_url,
    ):
        mock_settings.return_value.redis_url = url
        rate_limit_module._redis()

    mock_from_url.assert_called_once_with(
        "rediss://default:pw@example.upstash.io:6379/0",
        decode_responses=True,
        ssl_cert_reqs=ssl.CERT_NONE,
    )
    rate_limit_module._client = None


def test_redis_client_adds_no_tls_kwarg_for_plain_redis_url() -> None:
    rate_limit_module._client = None
    url = "redis://localhost:6380/0"

    with (
        patch.object(rate_limit_module, "get_settings") as mock_settings,
        patch("redis.asyncio.from_url") as mock_from_url,
    ):
        mock_settings.return_value.redis_url = url
        rate_limit_module._redis()

    mock_from_url.assert_called_once_with(url, decode_responses=True)
    rate_limit_module._client = None
