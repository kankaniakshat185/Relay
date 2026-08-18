"""Round-trips `engine/ingestion` (upsert/dedupe) and `engine/indexing`
(embed + hybrid search) against a real Postgres. OpenAI's embedding call is
mocked — this is testing the SQL, not the embedding model — but the actual
`to_tsvector`/`cosine_distance`/`ON CONFLICT` queries run for real.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.engine.indexing import service as indexing_service
from relay_api.engine.ingestion import service as ingestion_service
from relay_api.engine.ingestion.models import EMBEDDING_DIMENSIONS
from relay_api.engine.ingestion.schemas import NormalizedItem

_FAKE_VECTOR = [0.1] * EMBEDDING_DIMENSIONS


def _item(external_id: str, title: str = "Some PR") -> NormalizedItem:
    return NormalizedItem(
        source="github",
        source_type="pull_request",
        external_id=external_id,
        title=title,
        body="body text",
        url="https://github.com/acme/widgets/pull/1",
        author="octocat",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_upsert_then_reupsert_unchanged_is_not_flagged_dirty(
    db: AsyncSession, test_user: User
) -> None:
    item = _item("1")

    dirty_first = await ingestion_service.upsert_items(db, test_user.id, [item])
    assert len(dirty_first) == 1

    dirty_second = await ingestion_service.upsert_items(db, test_user.id, [item])
    assert dirty_second == []


async def test_content_change_reflags_and_clears_derived_data(
    db: AsyncSession, test_user: User
) -> None:
    await ingestion_service.upsert_items(db, test_user.id, [_item("2", title="Original title")])

    to_index = await ingestion_service.get_items_needing_indexing(db, test_user.id)
    with patch.object(indexing_service, "embed_texts", new=AsyncMock(return_value=[_FAKE_VECTOR])):
        await indexing_service.index_items(db, [i for i in to_index if i.external_id == "2"])

    dirty = await ingestion_service.upsert_items(
        db, test_user.id, [_item("2", title="Updated title")]
    )
    assert len(dirty) == 1

    still_unindexed = await ingestion_service.get_items_needing_indexing(db, test_user.id)
    assert any(i.external_id == "2" for i in still_unindexed)


async def test_index_then_search_finds_the_item(db: AsyncSession, test_user: User) -> None:
    await ingestion_service.upsert_items(db, test_user.id, [_item("3", title="Retry logic bug")])
    to_index = await ingestion_service.get_items_needing_indexing(db, test_user.id)

    with patch.object(indexing_service, "embed_texts", new=AsyncMock(return_value=[_FAKE_VECTOR])):
        await indexing_service.index_items(db, [i for i in to_index if i.external_id == "3"])
        results = await indexing_service.search(db, test_user.id, "retry logic", limit=5)

    assert any(r.external_id == "3" for r in results)


async def test_search_is_scoped_to_the_requesting_user(db: AsyncSession, test_user: User) -> None:
    # Randomized, not a fixed address — this insert commits durably (see
    # below), so a fixed email breaks on the second run against a
    # persistent local Postgres (fine in CI, which always starts fresh).
    other_user = User(email=f"{uuid.uuid4()}@example.com", display_name="Other User")
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    await ingestion_service.upsert_items(
        db, other_user.id, [_item("4", title="Someone else's item")]
    )
    to_index = await ingestion_service.get_items_needing_indexing(db, other_user.id)

    with patch.object(indexing_service, "embed_texts", new=AsyncMock(return_value=[_FAKE_VECTOR])):
        await indexing_service.index_items(db, to_index)
        results = await indexing_service.search(db, test_user.id, "item", limit=5)

    assert results == []
