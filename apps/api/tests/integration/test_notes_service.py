"""`features/notes/service.py` — every write mirrors into `ingested_items`
(ADR 0021), so this exercises the real DB, not mocks, for the mirroring
itself. Only the embedding call is mocked (same pattern as
`test_ingestion_and_indexing.py`) — this is testing that the mirror and
the search pipeline actually connect, not the embedding model.
"""

import uuid
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.engine.indexing import service as indexing_service
from relay_api.engine.indexing.embeddings import EmbeddingUnavailableError
from relay_api.engine.ingestion.models import EMBEDDING_DIMENSIONS, IngestedItem
from relay_api.features.context_search import service as context_search_service
from relay_api.features.notes import service as notes_service
from relay_api.features.notes.models import Note
from relay_api.features.notes.schemas import NoteCreate, NoteLink, NoteUpdate

_FAKE_VECTOR = [0.1] * EMBEDDING_DIMENSIONS


def _embed_mock() -> AsyncMock:
    return AsyncMock(return_value=[_FAKE_VECTOR])


async def test_creating_a_note_mirrors_it_into_ingested_items(
    db: AsyncSession, test_user: User
) -> None:
    with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
        note = await notes_service.create_note(
            db, test_user.id, NoteCreate(title="Retry logic notes", body="Why it retries 3x")
        )

    mirrored = await db.scalar(
        select(IngestedItem).where(
            IngestedItem.user_id == test_user.id,
            IngestedItem.source == "notes",
            IngestedItem.external_id == str(note.id),
        )
    )
    assert mirrored is not None
    assert mirrored.title == "Retry logic notes"
    assert mirrored.embedding is not None  # actually indexed, not just upserted


async def test_a_created_note_is_findable_via_context_search(
    db: AsyncSession, test_user: User
) -> None:
    with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
        await notes_service.create_note(
            db,
            test_user.id,
            NoteCreate(title="Payment retry decision", body="Chose exponential backoff"),
        )
        response = await context_search_service.search(
            db, test_user, "payment retry decision", use_llm=False
        )

    assert any(s.title == "Payment retry decision" for s in response.sources)


async def test_updating_title_reindexes_the_mirror(db: AsyncSession, test_user: User) -> None:
    with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
        note = await notes_service.create_note(
            db, test_user.id, NoteCreate(title="Old title", body="body")
        )
        await notes_service.update_note(db, test_user.id, note.id, NoteUpdate(title="New title"))

    mirrored = await db.scalar(
        select(IngestedItem).where(
            IngestedItem.user_id == test_user.id,
            IngestedItem.source == "notes",
            IngestedItem.external_id == str(note.id),
        )
    )
    assert mirrored is not None
    assert mirrored.title == "New title"


async def test_a_tags_only_update_does_not_needlessly_reembed(
    db: AsyncSession, test_user: User
) -> None:
    # `upsert_items` only flags a row dirty when title/body actually
    # changed — tags aren't mirrored onto title/body, so a tags-only edit
    # shouldn't trigger a second embed call.
    with patch.object(indexing_service, "embed_texts", new=_embed_mock()) as mock_embed:
        note = await notes_service.create_note(
            db, test_user.id, NoteCreate(title="Same title", body="Same body", tags=["a"])
        )
        mock_embed.reset_mock()
        await notes_service.update_note(db, test_user.id, note.id, NoteUpdate(tags=["a", "b"]))

    mock_embed.assert_not_awaited()


async def test_deleting_a_note_removes_both_rows(db: AsyncSession, test_user: User) -> None:
    with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
        note = await notes_service.create_note(
            db, test_user.id, NoteCreate(title="Temporary", body="body")
        )
        deleted = await notes_service.delete_note(db, test_user.id, note.id)

    assert deleted is True
    assert await notes_service.get_note(db, test_user.id, note.id) is None
    mirrored = await db.scalar(
        select(IngestedItem).where(
            IngestedItem.user_id == test_user.id,
            IngestedItem.source == "notes",
            IngestedItem.external_id == str(note.id),
        )
    )
    assert mirrored is None


async def test_delete_all_notes_removes_every_note_and_mirror(
    db: AsyncSession, test_user: User
) -> None:
    with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
        await notes_service.create_note(db, test_user.id, NoteCreate(title="First", body=""))
        await notes_service.create_note(db, test_user.id, NoteCreate(title="Second", body=""))

    deleted_count = await notes_service.delete_all_notes(db, test_user.id)

    assert deleted_count == 2
    assert await notes_service.list_notes(db, test_user.id) == []
    remaining_mirrors = await db.scalars(
        select(IngestedItem).where(
            IngestedItem.user_id == test_user.id, IngestedItem.source == "notes"
        )
    )
    assert list(remaining_mirrors) == []


async def test_delete_all_notes_on_an_empty_account_is_a_no_op(
    db: AsyncSession, test_user: User
) -> None:
    deleted_count = await notes_service.delete_all_notes(db, test_user.id)
    assert deleted_count == 0


async def test_delete_all_notes_does_not_touch_another_users_notes(
    db: AsyncSession, test_user: User
) -> None:
    other_user = User(email=f"{uuid.uuid4()}@example.com", display_name="Other")
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
        await notes_service.create_note(db, test_user.id, NoteCreate(title="Mine", body=""))
        await notes_service.create_note(db, other_user.id, NoteCreate(title="Theirs", body=""))

    deleted_count = await notes_service.delete_all_notes(db, test_user.id)

    assert deleted_count == 1
    remaining = await notes_service.list_notes(db, other_user.id)
    assert [n.title for n in remaining] == ["Theirs"]


async def test_an_embedding_failure_does_not_fail_the_note_save(
    db: AsyncSession, test_user: User
) -> None:
    with patch.object(
        indexing_service,
        "embed_texts",
        new=AsyncMock(side_effect=EmbeddingUnavailableError("quota exceeded")),
    ):
        note = await notes_service.create_note(
            db, test_user.id, NoteCreate(title="Saved anyway", body="body")
        )

    # The note itself is saved and readable...
    fetched = await notes_service.get_note(db, test_user.id, note.id)
    assert fetched is not None
    assert fetched.title == "Saved anyway"

    # ...even though its mirror is upserted but not yet embedded.
    mirrored = await db.scalar(
        select(IngestedItem).where(
            IngestedItem.user_id == test_user.id,
            IngestedItem.source == "notes",
            IngestedItem.external_id == str(note.id),
        )
    )
    assert mirrored is not None
    assert mirrored.embedding is None


async def test_list_notes_orders_most_recently_updated_first(
    db: AsyncSession, test_user: User
) -> None:
    with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
        first = await notes_service.create_note(
            db, test_user.id, NoteCreate(title="First", body="")
        )
        await notes_service.create_note(db, test_user.id, NoteCreate(title="Second", body=""))
        await notes_service.update_note(db, test_user.id, first.id, NoteUpdate(body="edited"))

    notes = await notes_service.list_notes(db, test_user.id)
    assert [n.title for n in notes] == ["First", "Second"]


def test_export_notes_markdown_includes_tags_and_linked_items() -> None:
    note = Note(
        title="Exported note",
        body="Some body text",
        tags=["backend", "flaky"],
        links=[
            {
                "source": "github",
                "url": "https://github.com/acme/widgets/pull/1",
                "title": "Fix retry logic",
            },
            {
                "source": "jira",
                "url": "https://acme.atlassian.net/browse/REL-42",
                "title": "REL-42",
            },
        ],
    )

    markdown = notes_service.export_notes_markdown([note])

    assert "## Exported note" in markdown
    assert "Tags: backend, flaky" in markdown
    assert "Linked (GitHub): [Fix retry logic](https://github.com/acme/widgets/pull/1)" in markdown
    assert "Linked (Jira): [REL-42](https://acme.atlassian.net/browse/REL-42)" in markdown
    assert "Some body text" in markdown


async def test_add_link_appends_without_touching_existing_links(
    db: AsyncSession, test_user: User
) -> None:
    with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
        note = await notes_service.create_note(
            db,
            test_user.id,
            NoteCreate(
                title="Multi-link note",
                body="",
                links=[
                    NoteLink(
                        source="github", url="https://github.com/acme/widgets/pull/1", title="PR"
                    )
                ],
            ),
        )

    updated = await notes_service.add_link(
        db,
        test_user.id,
        note.id,
        NoteLink(source="slack", url="https://acme.slack.com/archives/C1/p1", title="Thread"),
    )

    assert updated is not None
    assert [link["source"] for link in updated.links] == ["github", "slack"]


async def test_add_link_to_a_missing_note_returns_none(db: AsyncSession, test_user: User) -> None:
    result = await notes_service.add_link(
        db,
        test_user.id,
        uuid.uuid4(),
        NoteLink(source="github", url="https://github.com/acme/widgets", title="x"),
    )
    assert result is None


async def test_remove_link_by_index(db: AsyncSession, test_user: User) -> None:
    with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
        note = await notes_service.create_note(
            db,
            test_user.id,
            NoteCreate(
                title="Two links",
                body="",
                links=[
                    NoteLink(
                        source="github", url="https://github.com/acme/widgets/pull/1", title="PR"
                    ),
                    NoteLink(
                        source="jira", url="https://acme.atlassian.net/browse/REL-1", title="REL-1"
                    ),
                ],
            ),
        )

    updated = await notes_service.remove_link(db, test_user.id, note.id, 0)

    assert updated is not None
    assert [link["source"] for link in updated.links] == ["jira"]


async def test_remove_link_with_an_out_of_range_index_returns_none(
    db: AsyncSession, test_user: User
) -> None:
    with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
        note = await notes_service.create_note(
            db, test_user.id, NoteCreate(title="No links", body="")
        )

    result = await notes_service.remove_link(db, test_user.id, note.id, 0)

    assert result is None


async def test_remove_link_from_a_missing_note_returns_none(
    db: AsyncSession, test_user: User
) -> None:
    result = await notes_service.remove_link(db, test_user.id, uuid.uuid4(), 0)
    assert result is None
