"""`notes` — this feature's own store, mirrored (not moved) into
`engine.ingestion.models.IngestedItem` on every save so a note is
searchable/correlatable the same way real GitHub/Slack/Jira content is.
See ADR 0021 for why this is a separate table rather than writing
straight into `ingested_items`.

Column ownership: `features/notes/service.py` is the only writer and
reader.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from relay_api.core.db import Base


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)

    # `[{source, url, title}, ...]` — a note can reference several
    # GitHub/Slack/Jira items, not just one (added via "annotate this" →
    # create a new note, or → attach to an existing one). Denormalized
    # per entry, same reasoning as everywhere else in this feature: the
    # linked item can be re-ingested, change title, or fall out of the
    # connector's fetch window, and a note should still show what it
    # pointed at when the link was made, not go stale or break. JSONB, not
    # a separate table — same "small bag of denormalized references"
    # shape `WorkflowRun.pull_requests` already uses, no join needed to
    # render a note.
    links: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
