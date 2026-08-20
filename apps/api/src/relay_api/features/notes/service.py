"""Notes CRUD, with every write mirrored into `engine.ingestion`'s
`ingested_items` so a note is searchable/correlatable the same way real
GitHub/Slack/Jira content is — see ADR 0021 for why this is a mirror
into a separate table rather than notes living in `ingested_items`
directly.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.core.logging import get_logger
from relay_api.engine.indexing import service as indexing_service
from relay_api.engine.indexing.embeddings import EmbeddingUnavailableError
from relay_api.engine.ingestion import service as ingestion_service
from relay_api.engine.ingestion.models import IngestedItem
from relay_api.engine.ingestion.schemas import NormalizedItem, Source, SourceType
from relay_api.features.notes.models import Note
from relay_api.features.notes.schemas import NoteCreate, NoteLink, NoteUpdate

logger = get_logger(__name__)

_SOURCE: Source = "notes"
_SOURCE_TYPE: SourceType = "note"

_SOURCE_LABELS: dict[str, str] = {"github": "GitHub", "slack": "Slack", "jira": "Jira"}


async def _mirror_into_engine(db: AsyncSession, user_id: uuid.UUID, note: Note) -> None:
    """Upserts `note` into `ingested_items` and indexes it synchronously —
    one item, not the 15-minute Celery cadence every connector uses, since
    there's nothing external to poll: the note was just written directly.
    Embedding failure is caught, not raised — the note itself is already
    saved by the time this runs, and a save must not fail because of a
    downstream indexing hiccup (same discipline as Build 2's JUnit parser:
    a side effect degrades gracefully, it doesn't take the primary action
    down with it). A note that fails to index here stays fully usable from
    the Notes page; it just isn't searchable until the next edit retries
    this same path."""
    item = NormalizedItem(
        source=_SOURCE,
        source_type=_SOURCE_TYPE,
        external_id=str(note.id),
        title=note.title,
        body=note.body,
        # There's no per-note detail page (Notes is a flat list) — this
        # points at the list with a `highlight` param the page reads to
        # scroll to and mark the right row, rather than a `/notes/{id}`
        # URL that would 404.
        url=f"/notes?highlight={note.id}",
        author=None,
        occurred_at=note.updated_at or datetime.now(UTC),
    )
    dirty_ids = await ingestion_service.upsert_items(db, user_id, [item])
    if not dirty_ids:
        return

    result = await db.execute(select(IngestedItem).where(IngestedItem.id.in_(dirty_ids)))
    to_index = list(result.scalars().all())
    try:
        await indexing_service.index_items(db, to_index)
    except EmbeddingUnavailableError:
        logger.warning("note_indexing_failed", extra={"note_id": str(note.id)})


async def _delete_mirror(db: AsyncSession, user_id: uuid.UUID, note_id: uuid.UUID) -> None:
    await db.execute(
        delete(IngestedItem).where(
            IngestedItem.user_id == user_id,
            IngestedItem.source == _SOURCE,
            IngestedItem.source_type == _SOURCE_TYPE,
            IngestedItem.external_id == str(note_id),
        )
    )
    await db.commit()


async def create_note(db: AsyncSession, user_id: uuid.UUID, data: NoteCreate) -> Note:
    note = Note(
        user_id=user_id,
        title=data.title,
        body=data.body,
        tags=data.tags,
        links=[link.model_dump() for link in data.links],
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    await _mirror_into_engine(db, user_id, note)
    return note


async def list_notes(db: AsyncSession, user_id: uuid.UUID) -> list[Note]:
    result = await db.execute(
        select(Note).where(Note.user_id == user_id).order_by(Note.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_note(db: AsyncSession, user_id: uuid.UUID, note_id: uuid.UUID) -> Note | None:
    note: Note | None = await db.scalar(
        select(Note).where(Note.id == note_id, Note.user_id == user_id)
    )
    return note


async def update_note(
    db: AsyncSession, user_id: uuid.UUID, note_id: uuid.UUID, data: NoteUpdate
) -> Note | None:
    note = await get_note(db, user_id, note_id)
    if note is None:
        return None

    if data.title is not None:
        note.title = data.title
    if data.body is not None:
        note.body = data.body
    if data.tags is not None:
        note.tags = data.tags

    await db.commit()
    await db.refresh(note)

    await _mirror_into_engine(db, user_id, note)
    return note


async def add_link(
    db: AsyncSession, user_id: uuid.UUID, note_id: uuid.UUID, link: NoteLink
) -> Note | None:
    """The "attach to an existing note" half of the annotate flow — the
    other half is `create_note` seeding `links` at creation. Appends
    unconditionally (a note can reference the same item twice if the user
    really does that; not worth guarding against for the value it'd add).
    Doesn't touch title/body, so it doesn't re-trigger `_mirror_into_engine`
    — a link is display-only metadata as far as search/indexing is
    concerned, same as tags."""
    note = await get_note(db, user_id, note_id)
    if note is None:
        return None

    note.links = [*note.links, link.model_dump()]
    await db.commit()
    await db.refresh(note)
    return note


async def remove_link(
    db: AsyncSession, user_id: uuid.UUID, note_id: uuid.UUID, link_index: int
) -> Note | None:
    """The inverse of `add_link` — by index, not by (source, url) match,
    since a note can in principle reference the same item twice and a
    content match wouldn't unambiguously say which one to drop. Returns
    `None` for either "no such note" or "no such index on this note" —
    both are the same 404 to the caller, and the distinction isn't worth
    a separate error shape."""
    note = await get_note(db, user_id, note_id)
    if note is None or not (0 <= link_index < len(note.links)):
        return None

    note.links = [*note.links[:link_index], *note.links[link_index + 1 :]]
    await db.commit()
    await db.refresh(note)
    return note


async def delete_note(db: AsyncSession, user_id: uuid.UUID, note_id: uuid.UUID) -> bool:
    note = await get_note(db, user_id, note_id)
    if note is None:
        return False

    await db.delete(note)
    await db.commit()
    await _delete_mirror(db, user_id, note_id)
    return True


async def delete_all_notes(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Deletes every note this user has, and every mirrored
    `ingested_items` row alongside them — a single bulk delete on each
    table rather than looping `delete_note` per note, since there's no
    per-note logic here worth repeating N times. Returns how many notes
    were deleted, so the frontend can show a real count rather than a
    silent success."""
    notes = await list_notes(db, user_id)
    if not notes:
        return 0

    for note in notes:
        await db.delete(note)
    await db.commit()

    await db.execute(
        delete(IngestedItem).where(
            IngestedItem.user_id == user_id,
            IngestedItem.source == _SOURCE,
            IngestedItem.source_type == _SOURCE_TYPE,
        )
    )
    await db.commit()
    return len(notes)


def export_notes_markdown(notes: list[Note]) -> str:
    """One `## title` block per note, most recently updated first (same
    order `list_notes` returns) — tags and any linked items as plain
    lines underneath when present, each labeled with its source (GitHub/
    Slack/Jira), so the export reads as a normal markdown document, not a
    data dump."""
    blocks = []
    for note in notes:
        lines = [f"## {note.title}", ""]
        if note.tags:
            lines.append(f"*Tags: {', '.join(note.tags)}*")
        for link in note.links:
            source_label = _SOURCE_LABELS.get(link["source"], link["source"])
            lines.append(f"*Linked ({source_label}): [{link['title']}]({link['url']})*")
        if note.tags or note.links:
            lines.append("")
        lines.append(note.body)
        blocks.append("\n".join(lines))

    return "\n\n---\n\n".join(blocks)
