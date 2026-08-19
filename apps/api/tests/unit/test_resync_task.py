"""`_enqueue_resync_for_all_connectors` is deliberately thin — read who's
connected to what, re-enqueue the existing per-connector task for each.
No indexing logic to test here (that's `test_ingestion_and_indexing.py`'s
job); this only checks the fan-out itself."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from relay_api.connectors.models import ConnectorCredential
from relay_api.jobs import indexing


def _credential(user_id: uuid.UUID, provider: str) -> ConnectorCredential:
    return ConnectorCredential(
        user_id=user_id,
        provider=provider,
        access_token_encrypted="x",
        scope="",
        external_account_id="1",
        external_account_label="label",
    )


async def test_enqueues_one_task_per_connected_credential() -> None:
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    credentials = [
        _credential(user_a, "github"),
        _credential(user_a, "slack"),
        _credential(user_b, "jira"),
    ]

    with (
        patch.object(indexing, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(
            indexing,
            "async_session_factory",
            return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        ),
        patch.object(
            indexing.connector_service,
            "list_all_credentials",
            new=AsyncMock(return_value=credentials),
        ),
        patch.object(indexing.index_connector_task, "delay") as mock_delay,
    ):
        count = await indexing._enqueue_resync_for_all_connectors()

    assert count == 3
    assert mock_delay.call_count == 3
    mock_delay.assert_any_call(str(user_a), "github")
    mock_delay.assert_any_call(str(user_a), "slack")
    mock_delay.assert_any_call(str(user_b), "jira")


async def test_no_connected_credentials_enqueues_nothing() -> None:
    with (
        patch.object(indexing, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(
            indexing,
            "async_session_factory",
            return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        ),
        patch.object(
            indexing.connector_service, "list_all_credentials", new=AsyncMock(return_value=[])
        ),
        patch.object(indexing.index_connector_task, "delay") as mock_delay,
    ):
        count = await indexing._enqueue_resync_for_all_connectors()

    assert count == 0
    mock_delay.assert_not_called()
