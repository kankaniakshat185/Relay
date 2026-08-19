"""`engine/correlation.find_related` against a real Postgres — specifically
the interaction between `_MIN_RELEVANCE_SCORE` and the exact-ticket-key
safety net (`_find_exact_ticket_key_matches`), which only really proves
itself with a real SQL score computation, not a mocked `engine_search`
boundary (see `tests/unit/engine/test_correlation.py` for that level).
"""

from datetime import UTC, datetime
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.engine.correlation import service as correlation_service
from relay_api.engine.indexing import service as indexing_service
from relay_api.engine.ingestion import service as ingestion_service
from relay_api.engine.ingestion.models import EMBEDDING_DIMENSIONS
from relay_api.engine.ingestion.schemas import NormalizedItem


def _one_hot(dim: int) -> list[float]:
    v = [0.0] * EMBEDDING_DIMENSIONS
    v[dim] = 1.0
    return v


# Orthogonal to the query vector below — vector_similarity 0, so even with
# a real keyword hit, the blended score can't clear a threshold much above
# `_KEYWORD_WEIGHT`'s own ceiling. Deterministic, not dependent on a real
# embedding model actually placing these far apart.
_QUERY_VECTOR = _one_hot(0)
_FAR_VECTOR = _one_hot(1)


async def test_an_exact_ticket_key_mention_surfaces_despite_a_weak_vector_score(
    db: AsyncSession, test_user: User
) -> None:
    """The gap `_find_exact_ticket_key_matches` closes: a real, unambiguous
    keyword hit ("REL-42" literally in the message) whose vector
    similarity happens to be weak for that specific text pairing must
    still surface — it shouldn't depend on the blended score alone."""
    message = NormalizedItem(
        source="slack",
        source_type="message",
        external_id="msg-1",
        title="any updates on REL-42?",
        body="any updates on REL-42?",
        url="https://acme.slack.com/archives/C1/p1",
        author="alice",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await ingestion_service.upsert_items(db, test_user.id, [message])
    to_index = await ingestion_service.get_items_needing_indexing(db, test_user.id)

    async def _fake_embed(texts: list[str]) -> list[list[float]]:
        return [_FAR_VECTOR for _ in texts]

    with patch.object(indexing_service, "embed_texts", new=_fake_embed):
        await indexing_service.index_items(db, to_index)

        async def _fake_query_embed(texts: list[str]) -> list[list[float]]:
            return [_QUERY_VECTOR for _ in texts]

        with patch.object(indexing_service, "embed_texts", new=_fake_query_embed):
            # Sanity check: the general (non-exact) path really would have
            # dropped this — proves the test is actually exercising the
            # gap, not passing for an unrelated reason.
            without_safety_net = await indexing_service.search(
                db,
                test_user.id,
                "REL-42",
                sources=["slack"],
                min_score=correlation_service._MIN_RELEVANCE_SCORE,
            )
            assert without_safety_net == []

            result = await correlation_service.find_related(
                db, test_user.id, "REL-42", sources=["slack"]
            )

    assert [r.url for r in result] == [message.url]


async def test_unrelated_content_with_no_exact_match_still_gets_filtered(
    db: AsyncSession, test_user: User
) -> None:
    """The other half of the same interaction: something with no literal
    ticket-key mention and a weak score is still dropped — the safety net
    only rescues genuine keyword hits, it doesn't disable the threshold."""
    message = NormalizedItem(
        source="slack",
        source_type="message",
        external_id="msg-2",
        title="unrelated topic entirely",
        body="unrelated topic entirely",
        url="https://acme.slack.com/archives/C1/p2",
        author="alice",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await ingestion_service.upsert_items(db, test_user.id, [message])
    to_index = await ingestion_service.get_items_needing_indexing(db, test_user.id)

    async def _fake_embed(texts: list[str]) -> list[list[float]]:
        return [_FAR_VECTOR for _ in texts]

    with patch.object(indexing_service, "embed_texts", new=_fake_embed):
        await indexing_service.index_items(db, to_index)

        async def _fake_query_embed(texts: list[str]) -> list[list[float]]:
            return [_QUERY_VECTOR for _ in texts]

        with patch.object(indexing_service, "embed_texts", new=_fake_query_embed):
            result = await correlation_service.find_related(
                db, test_user.id, "REL-42", sources=["slack"]
            )

    assert result == []
