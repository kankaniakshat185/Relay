"""Indexing (embed + tsvector) and hybrid search over `ingested_items`.

Phase 1 scope only: this combines keyword and vector scores with a fixed
weighting. Comparing *strategies* for combining/ranking them is explicitly
`engine/ranking`'s job (Phase 2, differential-tested — see plan.md §6 and
ADR 0005) — this module's search is deliberately simple so Phase 2 has a
real baseline to differential-test against, not because it's unfinished.
"""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.engine.indexing.embeddings import embed_texts
from relay_api.engine.ingestion.models import IngestedItem

_KEYWORD_WEIGHT = 0.4
_VECTOR_WEIGHT = 0.6


async def index_items(db: AsyncSession, items: list[IngestedItem]) -> None:
    """Computes and stores embedding + search_vector for each item.
    Items are expected to have `embedding IS NULL` (see
    `engine/ingestion/service.get_items_needing_indexing`)."""
    if not items:
        return

    texts = [f"{item.title}\n\n{item.body}" for item in items]
    vectors = await embed_texts(texts)

    for item, text, vector in zip(items, texts, vectors, strict=True):
        await db.execute(
            update(IngestedItem)
            .where(IngestedItem.id == item.id)
            .values(embedding=vector, search_vector=func.to_tsvector("english", text))
        )

    await db.commit()


async def search(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    *,
    limit: int = 10,
    sources: list[str] | None = None,
) -> list[IngestedItem]:
    """Hybrid keyword + vector search, scoped to one user's ingested items."""
    query_embedding = (await embed_texts([query]))[0]
    ts_query = func.plainto_tsquery("english", query)

    keyword_rank = func.ts_rank(IngestedItem.search_vector, ts_query)
    vector_similarity = 1 - IngestedItem.embedding.cosine_distance(query_embedding)
    combined_score = (_KEYWORD_WEIGHT * keyword_rank) + (_VECTOR_WEIGHT * vector_similarity)

    stmt = select(IngestedItem).where(
        IngestedItem.user_id == user_id,
        IngestedItem.embedding.is_not(None),
    )
    if sources:
        stmt = stmt.where(IngestedItem.source.in_(sources))

    stmt = stmt.order_by(combined_score.desc()).limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())
