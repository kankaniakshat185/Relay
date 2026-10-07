"""Moved from `tests/unit/test_celery_app.py` when `tls_config_if_needed`
moved to `core/redis_tls.py` (a second Redis client needed the same fix —
see that module's docstring). `sanitized_redis_url`'s tests guard the bug
found live in production: a `rediss://` URL whose querystring carries a
broken `ssl_cert_reqs` value crashes `redis.asyncio`'s client even when
the correct value is also passed as an explicit keyword argument."""

import ssl

from relay_api.core.redis_tls import sanitized_redis_url, tls_config_if_needed


def test_tls_config_is_none_for_plain_redis_url() -> None:
    # Local dev (docker run redis:7-alpine) — no TLS involved at all.
    assert tls_config_if_needed("redis://localhost:6379/0") is None


def test_tls_config_sets_cert_none_for_rediss_url() -> None:
    # Upstash's production connection strings use rediss:// — kombu's
    # redis transport raises ValueError on connect without this.
    config = tls_config_if_needed("rediss://default:pw@example.upstash.io:6379")
    assert config == {"ssl_cert_reqs": ssl.CERT_NONE}


def test_sanitized_url_strips_ssl_cert_reqs() -> None:
    # The exact production shape: `ssl_cert_reqs=CERT_NONE` (the Python
    # enum's name) in the querystring, which redis-py rejects outright —
    # it only accepts "none"/"optional"/"required" there.
    url = "rediss://default:pw@example.upstash.io:6379/0?ssl_cert_reqs=CERT_NONE"
    assert sanitized_redis_url(url) == "rediss://default:pw@example.upstash.io:6379/0"


def test_sanitized_url_leaves_other_query_params_alone() -> None:
    url = "redis://localhost:6379/0?decode_responses=true"
    assert sanitized_redis_url(url) == url


def test_sanitized_url_is_unchanged_with_no_query_string() -> None:
    url = "redis://localhost:6379/0"
    assert sanitized_redis_url(url) == url
