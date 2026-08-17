"""Persists `NormalizedItem`s into `ingested_items`. This is the only
place connector output is written to the engine's storage — connectors
never touch the database directly (see `connectors/*/client.py`, which
only talks to provider APIs)."""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.engine.ingestion.models import IngestedItem
from relay_api.engine.ingestion.schemas import NormalizedItem


async def upsert_items(
    db: AsyncSession, user_id: uuid.UUID, items: list[NormalizedItem]
) -> list[uuid.UUID]:
    """Upserts by (user_id, source, source_type, external_id) — re-ingesting
    the same item (e.g. a PR that got updated) overwrites content but does
    NOT touch embedding/search_vector, since those go stale and need
    `engine/indexing` to re-run. Returns the ids of rows that are new or
    changed, so the caller knows what still needs (re-)indexing.
    """
    if not items:
        return []

    dirty_ids: list[uuid.UUID] = []

    for item in items:
        stmt = (
            insert(IngestedItem)
            .values(
                user_id=user_id,
                source=item.source,
                source_type=item.source_type,
                external_id=item.external_id,
                title=item.title,
                body=item.body,
                url=item.url,
                author=item.author,
                occurred_at=item.occurred_at,
                extra=item.extra,
            )
            .on_conflict_do_update(
                constraint="uq_ingested_item_identity",
                set_={
                    "title": item.title,
                    "body": item.body,
                    "url": item.url,
                    "author": item.author,
                    "occurred_at": item.occurred_at,
                    "extra": item.extra,
                    # Clear stale derived data so indexing knows to redo it.
                    "embedding": None,
                    "search_vector": None,
                },
                where=(IngestedItem.title != item.title) | (IngestedItem.body != item.body),
            )
            .returning(IngestedItem.id)
        )
        result = await db.execute(stmt)
        row = result.first()
        if row is not None:
            dirty_ids.append(row[0])

    await db.commit()
    return dirty_ids


async def get_items_needing_indexing(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 500
) -> list[IngestedItem]:
    result = await db.execute(
        select(IngestedItem)
        .where(IngestedItem.user_id == user_id, IngestedItem.embedding.is_(None))
        .limit(limit)
    )
    return list(result.scalars().all())
