"""`_enqueue_flaky_tests_sync_for_all_users` — deliberately thin, same
shape as `test_resync_task.py`'s coverage of the indexing pipeline's own
fan-out. One task per *user* connected to GitHub (not per user+provider —
this feature only ever reads GitHub), no indexing logic to test here."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from relay_api.connectors.models import ConnectorCredential
from relay_api.jobs import flaky_tests


def _credential(user_id: uuid.UUID, provider: str) -> ConnectorCredential:
    return ConnectorCredential(
        user_id=user_id,
        provider=provider,
        access_token_encrypted="x",
        scope="",
        external_account_id="1",
        external_account_label="label",
    )


async def test_enqueues_one_task_per_github_connected_user() -> None:
    user_a, user_b, user_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    credentials = [
        _credential(user_a, "github"),
        _credential(user_a, "slack"),  # same user, different provider — still one task
        _credential(user_b, "github"),
        _credential(user_c, "jira"),  # no GitHub — no task for this user
    ]

    with (
        patch.object(flaky_tests, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(
            flaky_tests,
            "async_session_factory",
            return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        ),
        patch.object(
            flaky_tests.connector_service,
            "list_all_credentials",
            new=AsyncMock(return_value=credentials),
        ),
        patch.object(flaky_tests.sync_flaky_tests_task, "delay") as mock_delay,
    ):
        count = await flaky_tests._enqueue_flaky_tests_sync_for_all_users()

    assert count == 2
    mock_delay.assert_any_call(str(user_a))
    mock_delay.assert_any_call(str(user_b))
    assert mock_delay.call_count == 2


async def test_no_github_credentials_enqueues_nothing() -> None:
    with (
        patch.object(flaky_tests, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(
            flaky_tests,
            "async_session_factory",
            return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        ),
        patch.object(
            flaky_tests.connector_service,
            "list_all_credentials",
            new=AsyncMock(return_value=[_credential(uuid.uuid4(), "slack")]),
        ),
        patch.object(flaky_tests.sync_flaky_tests_task, "delay") as mock_delay,
    ):
        count = await flaky_tests._enqueue_flaky_tests_sync_for_all_users()

    assert count == 0
    mock_delay.assert_not_called()
