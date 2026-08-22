"""`jobs.indexing._run_indexing_for_connector` — the actual per-connector
job (fetch → ingest → index → mark synced), run for real against Postgres
with only the live provider call and the embedding call mocked. Separate
from `test_ingestion_and_indexing.py`, which tests `engine/ingestion` and
`engine/indexing` directly, not this orchestration wrapper.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors import service as connector_service
from relay_api.connectors.encryption import encrypt_token
from relay_api.connectors.models import ConnectorCredential
from relay_api.engine.indexing import service as indexing_service
from relay_api.engine.ingestion.models import EMBEDDING_DIMENSIONS
from relay_api.jobs import indexing as indexing_job

_FAKE_VECTOR = [0.1] * EMBEDDING_DIMENSIONS


async def _empty_batches(*_args: object, **_kwargs: object) -> AsyncIterator[list[object]]:
    """Stands in for `_iter_item_batches` when a test only cares about the
    rest of the run (last-synced bookkeeping, etc.), not what got fetched —
    an async generator that immediately stops, same as a real provider
    with nothing new to report."""
    return
    yield  # pragma: no cover - makes this an async generator, never reached


class _SameSessionCM:
    """`_run_indexing_for_connector` opens its own session via
    `async_session_factory()` rather than taking one as a parameter (it's
    a Celery task body, not a request handler) — hands back this test's
    own `db` fixture session instead of a real new one, so writes are
    visible to the assertions below without a second, separate
    connection."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def __aenter__(self) -> AsyncSession:
        return self._db

    async def __aexit__(self, *exc_info: object) -> None:
        return None


async def _connect_github(db: AsyncSession, user: User) -> ConnectorCredential:
    credential = ConnectorCredential(
        user_id=user.id,
        provider="github",
        access_token_encrypted=encrypt_token("gh-token"),
        scope="repo",
        external_account_id="1",
        external_account_label="octocat",
    )
    db.add(credential)
    await db.commit()
    await db.refresh(credential)
    return credential


async def test_a_successful_run_sets_last_synced_at(db: AsyncSession, test_user: User) -> None:
    await _connect_github(db, test_user)

    with (
        patch.object(indexing_job, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(indexing_job, "async_session_factory", return_value=_SameSessionCM(db)),
        patch.object(indexing_job, "_iter_item_batches", new=_empty_batches),
        patch.object(indexing_service, "embed_texts", new=AsyncMock(return_value=[_FAKE_VECTOR])),
    ):
        await indexing_job._run_indexing_for_connector(test_user.id, "github")

    credential = await connector_service.get_credential(db, test_user.id, "github")
    assert credential is not None
    assert credential.last_synced_at is not None
    assert datetime.now(UTC) - credential.last_synced_at < timedelta(seconds=10)


async def test_last_synced_at_updates_even_when_nothing_new_was_found(
    db: AsyncSession, test_user: User
) -> None:
    # The honest-freshness-signal point from the column's own docstring:
    # a sync that finds zero new/changed items still counts as "synced."
    credential = await _connect_github(db, test_user)
    stale = datetime.now(UTC) - timedelta(days=1)
    credential.last_synced_at = stale
    await db.commit()

    with (
        patch.object(indexing_job, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(indexing_job, "async_session_factory", return_value=_SameSessionCM(db)),
        patch.object(indexing_job, "_iter_item_batches", new=_empty_batches),
        patch.object(indexing_service, "embed_texts", new=AsyncMock(return_value=[_FAKE_VECTOR])),
    ):
        await indexing_job._run_indexing_for_connector(test_user.id, "github")

    refreshed = await connector_service.get_credential(db, test_user.id, "github")
    assert refreshed is not None
    assert refreshed.last_synced_at is not None
    assert refreshed.last_synced_at > stale
