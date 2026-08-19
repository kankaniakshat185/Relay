"""The refresh-and-persist path of `ensure_valid_access_token` — needs a
real, committed `ConnectorCredential` row (FK to a real user, and the
assertions reload it from the DB) so it's an integration test, not unit.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors import service as connector_service
from relay_api.connectors.base import RefreshedTokens, RefreshGrantError
from relay_api.connectors.encryption import decrypt_token, encrypt_token
from relay_api.connectors.models import ConnectorCredential
from relay_api.connectors.registry import get_refreshable_provider


async def _jira_credential(db: AsyncSession, user: User, *, expired: bool) -> ConnectorCredential:
    credential = ConnectorCredential(
        id=uuid.uuid4(),
        user_id=user.id,
        provider="jira",
        access_token_encrypted=encrypt_token("stale-access"),
        refresh_token_encrypted=encrypt_token("old-refresh"),
        scope="read:jira-work read:jira-user offline_access",
        expires_at=datetime.now(UTC) + (timedelta(seconds=-1) if expired else timedelta(hours=1)),
        external_account_id="cloud-id-1",
        external_account_label="acme.atlassian.net",
    )
    db.add(credential)
    await db.commit()
    await db.refresh(credential)
    return credential


async def test_expired_jira_token_is_refreshed_and_persisted(
    db: AsyncSession, test_user: User
) -> None:
    credential = await _jira_credential(db, test_user, expired=True)
    jira_provider = get_refreshable_provider("jira")
    assert jira_provider is not None

    new_expiry = datetime.now(UTC) + timedelta(hours=1)
    with patch.object(
        jira_provider,
        "refresh_access_token",
        new=AsyncMock(
            return_value=RefreshedTokens(
                access_token="fresh-access",
                refresh_token="fresh-refresh",
                expires_at=new_expiry,
            )
        ),
    ):
        token = await connector_service.ensure_valid_access_token(db, credential)

    assert token == "fresh-access"

    reloaded = await connector_service.get_credential(db, test_user.id, "jira")
    assert reloaded is not None
    assert decrypt_token(reloaded.access_token_encrypted) == "fresh-access"
    assert reloaded.refresh_token_encrypted is not None
    assert decrypt_token(reloaded.refresh_token_encrypted) == "fresh-refresh"
    assert reloaded.expires_at is not None
    assert reloaded.expires_at.replace(microsecond=0) == new_expiry.replace(microsecond=0)


async def test_still_valid_jira_token_is_not_refreshed(db: AsyncSession, test_user: User) -> None:
    credential = await _jira_credential(db, test_user, expired=False)
    jira_provider = get_refreshable_provider("jira")
    assert jira_provider is not None

    with patch.object(jira_provider, "refresh_access_token", new=AsyncMock()) as mock_refresh:
        token = await connector_service.ensure_valid_access_token(db, credential)

    mock_refresh.assert_not_called()
    assert token == "stale-access"


async def _github_credential(db: AsyncSession, user: User, *, expired: bool) -> ConnectorCredential:
    # The real-world case this covers: a GitHub OAuth App with "expire
    # user authorization tokens" turned on — most don't have this set,
    # but the one this project connects against does (found live, Phase
    # 2 retro). expires_at is only ever non-null here in that case.
    credential = ConnectorCredential(
        id=uuid.uuid4(),
        user_id=user.id,
        provider="github",
        access_token_encrypted=encrypt_token("stale-access"),
        refresh_token_encrypted=encrypt_token("old-refresh"),
        scope="repo read:org read:user",
        expires_at=datetime.now(UTC) + (timedelta(seconds=-1) if expired else timedelta(hours=1)),
        external_account_id="1",
        external_account_label="octocat",
    )
    db.add(credential)
    await db.commit()
    await db.refresh(credential)
    return credential


async def test_expired_github_token_is_refreshed_and_persisted(
    db: AsyncSession, test_user: User
) -> None:
    credential = await _github_credential(db, test_user, expired=True)
    github_provider = get_refreshable_provider("github")
    assert github_provider is not None

    new_expiry = datetime.now(UTC) + timedelta(hours=8)
    with patch.object(
        github_provider,
        "refresh_access_token",
        new=AsyncMock(
            return_value=RefreshedTokens(
                access_token="fresh-access", refresh_token="fresh-refresh", expires_at=new_expiry
            )
        ),
    ):
        token = await connector_service.ensure_valid_access_token(db, credential)

    assert token == "fresh-access"
    reloaded = await connector_service.get_credential(db, test_user.id, "github")
    assert reloaded is not None
    assert decrypt_token(reloaded.access_token_encrypted) == "fresh-access"


async def test_github_refresh_grant_rejection_raises_token_refresh_error(
    db: AsyncSession, test_user: User
) -> None:
    # GitHub's own error-signaling convention (200 + `error` body field,
    # not an HTTP error status) — this is what `RefreshGrantError` exists
    # to normalize; asserting it here proves `ensure_valid_access_token`
    # actually catches it, not just `httpx.HTTPStatusError`.
    credential = await _github_credential(db, test_user, expired=True)
    github_provider = get_refreshable_provider("github")
    assert github_provider is not None

    with (
        patch.object(
            github_provider,
            "refresh_access_token",
            new=AsyncMock(side_effect=RefreshGrantError("bad_refresh_token")),
        ),
        pytest.raises(connector_service.TokenRefreshError),
    ):
        await connector_service.ensure_valid_access_token(db, credential)
