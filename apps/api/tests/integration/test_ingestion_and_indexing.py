"""Round-trips `engine/ingestion` (upsert/dedupe) and `engine/indexing`
(embed + hybrid search) against a real Postgres. OpenAI's embedding call is
mocked — this is testing the SQL, not the embedding model — but the actual
`to_tsvector`/`cosine_distance`/`ON CONFLICT` queries run for real.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.engine.indexing import service as indexing_service
from relay_api.engine.indexing.embeddings import EmbeddingUnavailableError
from relay_api.engine.ingestion import service as ingestion_service
from relay_api.engine.ingestion.models import EMBEDDING_DIMENSIONS, IngestedItem
from relay_api.engine.ingestion.schemas import NormalizedItem

_FAKE_VECTOR = [0.1] * EMBEDDING_DIMENSIONS


def _one_hot(dim: int) -> list[float]:
    v = [0.0] * EMBEDDING_DIMENSIONS
    v[dim] = 1.0
    return v


# Orthogonal one-hot vectors — cosine_distance between them is exactly 1
# (vector_similarity 0), and identical to itself is exactly 0 (vector_similarity
# 1), giving deterministic, easy-to-reason-about combined scores for the
# min_score test below, unlike two arbitrary real embeddings.
_CLOSE_VECTOR = _one_hot(0)
_FAR_VECTOR = _one_hot(1)


def _item(
    external_id: str,
    title: str = "Some PR",
    occurred_at: datetime = datetime(2026, 1, 1, tzinfo=UTC),
) -> NormalizedItem:
    return NormalizedItem(
        source="github",
        source_type="pull_request",
        external_id=external_id,
        title=title,
        body="body text",
        url="https://github.com/acme/widgets/pull/1",
        author="octocat",
        occurred_at=occurred_at,
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


async def test_search_source_types_narrows_within_a_source(
    db: AsyncSession, test_user: User
) -> None:
    # Both `source="github"` — `sources=["github"]` alone can't tell them
    # apart; `source_types` is what `engine.correlation.find_related`
    # threads through for `features/decision_debt` (ADR 0027).
    pr = NormalizedItem(
        source="github",
        source_type="pull_request",
        external_id="pr-src-type",
        title="Retry logic bug",
        body="Retry logic bug",
        url="https://github.com/acme/widgets/pull/9",
        author="octocat",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    doc = NormalizedItem(
        source="github",
        source_type="decision_doc",
        external_id="decision-doc-src-type",
        title="Retry logic bug",
        body="Retry logic bug",
        url="https://github.com/acme/widgets/blob/HEAD/docs/adr/0002.md",
        author="octocat",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await ingestion_service.upsert_items(db, test_user.id, [pr, doc])
    to_index = await ingestion_service.get_items_needing_indexing(db, test_user.id)

    async def _fake_embed(texts: list[str]) -> list[list[float]]:
        return [_FAKE_VECTOR for _ in texts]

    with patch.object(indexing_service, "embed_texts", new=_fake_embed):
        await indexing_service.index_items(db, to_index)
        results = await indexing_service.search(
            db, test_user.id, "retry logic", sources=["github"], source_types=["decision_doc"]
        )

    assert {r.external_id for r in results} == {"decision-doc-src-type"}


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


async def test_a_later_chunk_failing_does_not_discard_an_earlier_chunk_already_committed(
    db: AsyncSession, test_user: User
) -> None:
    """Regression test: `index_items` used to compute embeddings for its
    *entire* input in one `embed_texts` call and only write to the DB
    after that whole call succeeded — a failure partway through silently
    discarded every embedding already computed before it, and since the
    next indexing run re-fetches the same "needs indexing" set, a backlog
    larger than one provider quota window could never shrink at all.
    Found live when raising GitHub ingestion limits produced a 700+-item
    backlog that outran Gemini's free-tier embedding quota."""
    chunk_size = indexing_service._INDEX_CHUNK_SIZE
    items = [_item(str(i), title=f"Item {i}") for i in range(chunk_size + 1)]
    await ingestion_service.upsert_items(db, test_user.id, items)
    to_index = await ingestion_service.get_items_needing_indexing(db, test_user.id)
    assert len(to_index) == chunk_size + 1

    # First chunk (chunk_size items) succeeds; the second chunk (the
    # remaining 1 item) fails — simulating a rate limit hit partway
    # through a backlog larger than one chunk.
    call_count = 0

    async def _fake_embed_texts(texts: list[str]) -> list[list[float]]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [_FAKE_VECTOR for _ in texts]
        raise EmbeddingUnavailableError("429 rate limited")

    with (
        patch.object(indexing_service, "embed_texts", new=_fake_embed_texts),
        pytest.raises(EmbeddingUnavailableError),
    ):
        await indexing_service.index_items(db, to_index)

    result = await db.execute(
        select(IngestedItem)
        .where(IngestedItem.user_id == test_user.id)
        .order_by(IngestedItem.title)
    )
    by_title = {i.title: i for i in result.scalars().all()}
    first_chunk_titles = {f"Item {i}" for i in range(chunk_size)}
    last_item_title = f"Item {chunk_size}"

    assert all(by_title[t].embedding is not None for t in first_chunk_titles)
    assert by_title[last_item_title].embedding is None


async def test_search_min_score_drops_weak_matches_kept_by_a_plain_limit(
    db: AsyncSession, test_user: User
) -> None:
    """Regression test for the gap found live: with a small ingested
    corpus, `search()`'s `ORDER BY score LIMIT N` always returns N results
    regardless of relevance — "related Slack discussion" for a commit with
    zero real Slack activity was showing whatever few messages existed,
    just because they were "the top N," not because they were related.
    `min_score` lets a caller (`engine.correlation`) assert a real floor."""
    close_item = _item("close-1", title="Close match")
    far_item = _item("far-1", title="Unrelated item")
    await ingestion_service.upsert_items(db, test_user.id, [close_item, far_item])
    to_index = await ingestion_service.get_items_needing_indexing(db, test_user.id)

    async def _fake_embed(texts: list[str]) -> list[list[float]]:
        # The query text ("query") and the "close" item's text both embed
        # identically (cosine_distance 0); the "far" item embeds
        # orthogonally (cosine_distance 1) — deterministic separation, not
        # dependent on a real embedding model's actual behavior.
        return [_FAR_VECTOR if "Unrelated item" in t else _CLOSE_VECTOR for t in texts]

    with patch.object(indexing_service, "embed_texts", new=_fake_embed):
        await indexing_service.index_items(db, to_index)

        unfiltered = await indexing_service.search(db, test_user.id, "query", limit=10)
        filtered = await indexing_service.search(db, test_user.id, "query", limit=10, min_score=0.4)

    assert {i.title for i in unfiltered} == {"Close match", "Unrelated item"}
    assert {i.title for i in filtered} == {"Close match"}


async def test_get_items_since_only_returns_items_in_the_window(
    db: AsyncSession, test_user: User
) -> None:
    recent = _item(
        "recent-1", title="Inside the window", occurred_at=datetime.now(UTC) - timedelta(days=1)
    )
    stale = _item(
        "stale-1", title="Outside the window", occurred_at=datetime.now(UTC) - timedelta(days=30)
    )
    await ingestion_service.upsert_items(db, test_user.id, [recent, stale])

    results = await ingestion_service.get_items_since(
        db, test_user.id, datetime.now(UTC) - timedelta(days=7)
    )

    assert {i.title for i in results} == {"Inside the window"}


async def test_get_items_since_orders_most_recent_first(db: AsyncSession, test_user: User) -> None:
    older = _item("older-1", title="Older item", occurred_at=datetime.now(UTC) - timedelta(days=3))
    newer = _item("newer-1", title="Newer item", occurred_at=datetime.now(UTC) - timedelta(days=1))
    await ingestion_service.upsert_items(db, test_user.id, [older, newer])

    results = await ingestion_service.get_items_since(
        db, test_user.id, datetime.now(UTC) - timedelta(days=7)
    )

    titles = [i.title for i in results if i.title in {"Older item", "Newer item"}]
    assert titles == ["Newer item", "Older item"]


async def test_get_items_since_is_scoped_to_the_requesting_user(
    db: AsyncSession, test_user: User
) -> None:
    other_user = User(email=f"{uuid.uuid4()}@example.com", display_name="Other User")
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    item = _item(
        "other-1",
        title="Someone else's recent item",
        occurred_at=datetime.now(UTC) - timedelta(days=1),
    )
    await ingestion_service.upsert_items(db, other_user.id, [item])

    results = await ingestion_service.get_items_since(
        db, test_user.id, datetime.now(UTC) - timedelta(days=7)
    )

    assert all(i.title != "Someone else's recent item" for i in results)


async def test_get_items_since_with_until_bounds_both_sides_of_the_window(
    db: AsyncSession, test_user: User
) -> None:
    before = _item(
        "before-1", title="Before the window", occurred_at=datetime.now(UTC) - timedelta(days=10)
    )
    inside = _item(
        "inside-1", title="Inside the window", occurred_at=datetime.now(UTC) - timedelta(days=5)
    )
    after = _item(
        "after-1", title="After the window", occurred_at=datetime.now(UTC) - timedelta(days=1)
    )
    await ingestion_service.upsert_items(db, test_user.id, [before, inside, after])

    results = await ingestion_service.get_items_since(
        db,
        test_user.id,
        since=datetime.now(UTC) - timedelta(days=7),
        until=datetime.now(UTC) - timedelta(days=2),
    )

    assert {i.title for i in results} == {"Inside the window"}


async def test_get_items_since_respects_the_limit(db: AsyncSession, test_user: User) -> None:
    an_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    items = [
        _item(f"limit-{i}", title=f"Limit item {i}", occurred_at=an_hour_ago) for i in range(5)
    ]
    await ingestion_service.upsert_items(db, test_user.id, items)

    results = await ingestion_service.get_items_since(
        db, test_user.id, datetime.now(UTC) - timedelta(days=7), limit=3
    )

    assert len(results) == 3
