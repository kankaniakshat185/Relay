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

_INDEX_CHUNK_SIZE = 50
"""Embed and commit in chunks, not the whole call's `items` at once —
found live: raising GitHub ingestion's per-repo limits produced a
700+-item backlog in one resync, and Gemini's free-tier embedding quota
(100 requests/minute) rejected the request partway through. The old
all-or-nothing version computed `vectors` for the *entire* input in one
`embed_texts` call and only wrote to the DB after that whole call
succeeded — a failure on item 500 discarded the already-computed
embeddings for items 1-499 too, and since the next indexing run
re-fetches the exact same "needs indexing" set (`embedding IS NULL`),
that backlog could never shrink at all, not even slowly. Chunking here
means a mid-run failure still commits every chunk that succeeded before
it, so a backlog larger than one provider quota window drains over
several runs instead of stalling forever. Deliberately smaller than
`embed_texts`'s own internal `_MAX_BATCH_SIZE` (96, sized to fit under a
single provider call's item cap) so each chunk here is exactly one
provider call, not itself split further."""


async def index_items(db: AsyncSession, items: list[IngestedItem]) -> None:
    """Computes and stores embedding + search_vector for each item, in
    chunks of `_INDEX_CHUNK_SIZE` committed independently — see that
    constant's docstring for why. Items are expected to have `embedding
    IS NULL` (see `engine/ingestion/service.get_items_needing_indexing`).
    Raises `EmbeddingUnavailableError` on the first chunk that fails
    (not retried silently — see that exception's docstring); every prior
    chunk in this call is already committed by then."""
    if not items:
        return

    for start in range(0, len(items), _INDEX_CHUNK_SIZE):
        chunk = items[start : start + _INDEX_CHUNK_SIZE]
        texts = [f"{item.title}\n\n{item.body}" for item in chunk]
        vectors = await embed_texts(texts)

        for item, text, vector in zip(chunk, texts, vectors, strict=True):
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
    source_types: list[str] | None = None,
    min_score: float | None = None,
) -> list[IngestedItem]:
    """Hybrid keyword + vector search, scoped to one user's ingested items.

    `sources` filters the `source` column (github/slack/jira/notes);
    `source_types` filters `source_type` (pull_request/commit/message/...)
    — independent filters, both optional, combined with AND when both are
    given. Added for `features/decision_debt` (ADR 0027), which needs to
    search *within* `source="github"` for specifically `source_type=
    "decision_doc"` — `sources` alone can't express that, since every
    other GitHub source_type would match it too.

    `min_score`, if set, drops candidates below that combined score
    instead of always returning up to `limit` results regardless of how
    weak the match is. Left unset by default (and by
    `features/context_search`, its original caller) — raw retrieval mode
    is explicitly "show what's retrieved, as-is" (ADR 0008), so filtering
    there would be a behavior change no one asked for. `engine.correlation`
    sets it (see that module for the actual threshold and why): a caller
    that presents a result as "here's what's *related*" is asserting
    something raw retrieval never did, and with a small ingested corpus
    (found live with only 4 Slack messages total) "top N by score" can
    mean "the only N that exist," not "N genuinely related items.\""""
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
    if source_types:
        stmt = stmt.where(IngestedItem.source_type.in_(source_types))
    if min_score is not None:
        stmt = stmt.where(combined_score >= min_score)

    stmt = stmt.order_by(combined_score.desc()).limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())
