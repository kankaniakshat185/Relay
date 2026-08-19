"""`POST /v1/connectors/{provider}/sync` — router-level: real DB for the
credential/cooldown lookup, the actual Celery dispatch (`index_connector_task.delay`)
mocked, matching the same boundary `connectors/router.py`'s OAuth callback
already crosses at connect time.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors.encryption import encrypt_token
from relay_api.connectors.models import ConnectorCredential
from relay_api.core.deps import get_current_user
from relay_api.main import app


async def _connect_github(
    db: AsyncSession, user: User, *, last_synced_at: datetime | None = None
) -> None:
    db.add(
        ConnectorCredential(
            user_id=user.id,
            provider="github",
            access_token_encrypted=encrypt_token("gh-token"),
            scope="repo",
            external_account_id="1",
            external_account_label="octocat",
            last_synced_at=last_synced_at,
        )
    )
    await db.commit()


async def test_sync_requires_the_provider_to_be_connected(
    client: AsyncClient, test_user: User
) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        response = await client.post("/v1/connectors/github/sync")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400


async def test_sync_dispatches_the_indexing_task_and_returns_202(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)  # never synced — no cooldown

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch("relay_api.connectors.router.index_connector_task.delay") as mock_delay:
            response = await client.post("/v1/connectors/github/sync")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 202
    mock_delay.assert_called_once_with(str(test_user.id), "github")


async def test_sync_is_rejected_within_the_cooldown_window(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user, last_synced_at=datetime.now(UTC) - timedelta(seconds=5))

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch("relay_api.connectors.router.index_connector_task.delay") as mock_delay:
            response = await client.post("/v1/connectors/github/sync")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 429
    mock_delay.assert_not_called()


async def test_sync_is_allowed_once_the_cooldown_has_elapsed(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user, last_synced_at=datetime.now(UTC) - timedelta(minutes=10))

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch("relay_api.connectors.router.index_connector_task.delay") as mock_delay:
            response = await client.post("/v1/connectors/github/sync")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 202
    mock_delay.assert_called_once_with(str(test_user.id), "github")
