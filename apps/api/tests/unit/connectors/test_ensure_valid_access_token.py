"""`ensure_valid_access_token`'s early-return branches don't need a real
DB — they never call `db.commit()`. The actual refresh-and-persist path is
covered as an integration test (needs a real ConnectorCredential row), see
tests/integration/test_connector_token_refresh.py.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from relay_api.connectors import service
from relay_api.connectors.encryption import encrypt_token
from relay_api.connectors.models import ConnectorCredential


def _credential(
    provider: str = "jira",
    expires_at: datetime | None = None,
    has_refresh_token: bool = True,
) -> ConnectorCredential:
    return ConnectorCredential(
        provider=provider,
        access_token_encrypted=encrypt_token("stale-access"),
        refresh_token_encrypted=encrypt_token("some-refresh") if has_refresh_token else None,
        scope="read:jira-work",
        expires_at=expires_at,
        external_account_id="cloud-id",
        external_account_label="acme.atlassian.net",
    )


async def test_non_expiring_token_passes_through_untouched() -> None:
    credential = _credential(expires_at=None)
    db = MagicMock()

    token = await service.ensure_valid_access_token(db, credential)

    assert token == "stale-access"
    db.commit.assert_not_called()


async def test_token_not_yet_near_expiry_passes_through_untouched() -> None:
    credential = _credential(expires_at=datetime.now(UTC) + timedelta(hours=1))
    db = MagicMock()

    token = await service.ensure_valid_access_token(db, credential)

    assert token == "stale-access"
    db.commit.assert_not_called()


async def test_expired_token_for_a_non_refreshable_provider_passes_through_stale() -> None:
    # Slack's bot-install tokens don't expire — the one provider with no
    # `refresh_access_token` at all (GitHub is refreshable too now that
    # its OAuth App's optional token-expiration setting turned out to
    # matter in practice; see the Phase 2 retro).
    credential = _credential(provider="slack", expires_at=datetime.now(UTC) - timedelta(seconds=1))
    db = MagicMock()

    token = await service.ensure_valid_access_token(db, credential)

    assert token == "stale-access"
    db.commit.assert_not_called()


async def test_expired_token_with_no_stored_refresh_token_passes_through_stale() -> None:
    credential = _credential(
        expires_at=datetime.now(UTC) - timedelta(seconds=1), has_refresh_token=False
    )
    db = MagicMock()

    token = await service.ensure_valid_access_token(db, credential)

    assert token == "stale-access"
    db.commit.assert_not_called()


async def test_refresh_failure_raises_token_refresh_error(monkeypatch: pytest.MonkeyPatch) -> None:
    credential = _credential(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    db = MagicMock()
    db.commit = AsyncMock()

    fake_refreshable = MagicMock()
    request = httpx.Request("POST", "https://auth.atlassian.com/oauth/token")
    fake_refreshable.refresh_access_token = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "bad", request=request, response=httpx.Response(400, request=request)
        )
    )
    monkeypatch.setattr(service, "get_refreshable_provider", lambda _name: fake_refreshable)

    with pytest.raises(service.TokenRefreshError):
        await service.ensure_valid_access_token(db, credential)

    db.commit.assert_not_called()
