"""`connectors.service.check_sync_allowed` — the manual "Sync now" guard.
Pure function over a `ConnectorCredential`'s `last_synced_at`, no DB
needed to test it."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from relay_api.connectors import service
from relay_api.connectors.models import ConnectorCredential


def _credential(last_synced_at: datetime | None) -> ConnectorCredential:
    return ConnectorCredential(
        user_id=uuid.uuid4(),
        provider="github",
        access_token_encrypted="x",
        scope="",
        external_account_id="1",
        external_account_label="label",
        last_synced_at=last_synced_at,
    )


def test_allowed_when_never_synced_before() -> None:
    service.check_sync_allowed(_credential(last_synced_at=None))  # no raise


def test_allowed_once_the_cooldown_has_elapsed() -> None:
    long_ago = datetime.now(UTC) - service._SYNC_COOLDOWN - timedelta(seconds=1)

    service.check_sync_allowed(_credential(last_synced_at=long_ago))  # no raise


def test_blocked_within_the_cooldown_window() -> None:
    just_now = datetime.now(UTC) - timedelta(seconds=1)

    with pytest.raises(service.SyncCooldownError) as exc_info:
        service.check_sync_allowed(_credential(last_synced_at=just_now))

    # Roughly the full cooldown minus the second that already elapsed —
    # not asserting an exact value since real time passes during the test.
    assert 0 < exc_info.value.retry_after_seconds <= service._SYNC_COOLDOWN.total_seconds()
