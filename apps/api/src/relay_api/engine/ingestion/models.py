"""`ingested_items` — the one physical table every connector's normalized
output lands in, and the one table `engine/indexing` and (Phase 2)
`engine/ranking` read from. See `engine/ingestion/schemas.py` for the
normalized shape this table stores, and ADR 0006 for why `embedding` +
`search_vector` live on this table rather than a separate one: the engine
needs to filter (source, time range, entity) and rank (keyword + vector)
in a single query, not a join across two tables.

Column ownership, for when this file gets touched:
  - `engine/ingestion` writes: source, source_type, external_id, title,
    body, url, author, occurred_at, extra.
  - `engine/indexing` writes (async, after ingestion): embedding, search_vector.
"""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from relay_api.core.db import Base

EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small — see ADR 0006


class IngestedItem(Base):
    __tablename__ = "ingested_items"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "source", "source_type", "external_id", name="uq_ingested_item_identity"
        ),
        Index("ix_ingested_items_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_ingested_items_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    source: Mapped[str] = mapped_column(String(16))
    source_type: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(255))

    title: Mapped[str] = mapped_column(String(1024))
    body: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(2048))
    author: Mapped[str | None] = mapped_column(String(255), default=None)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # --- engine/indexing-owned, nullable until indexed (Phase 1 async step) ---
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), default=None
    )
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
