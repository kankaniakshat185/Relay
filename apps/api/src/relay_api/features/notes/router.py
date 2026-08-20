"""Notes endpoints (mounted under `/v1/notes`):
POST   /                        — create a note (optionally with initial links)
GET    /                        — list this user's notes, most recently updated first
GET    /export                  — all notes as one Markdown document
PATCH  /{note_id}               — edit title/body/tags
POST   /{note_id}/links         — attach one more link to an existing note
DELETE /{note_id}/links/{i}     — remove one link from a note, by its index
DELETE /{note_id}               — delete one
DELETE /                        — delete every note this user has

`/export` is declared before `/{note_id}` deliberately — Starlette
matches path templates in declaration order, so a `GET /notes/{note_id}`
route ahead of this would swallow `/notes/export` and fail UUID parsing
on the literal string "export" instead of ever reaching this handler.
`DELETE /` and `DELETE /{note_id}` don't have that hazard — a bare path
and a one-segment path are different templates, matched correctly
regardless of order — but the two live next to each other below anyway,
for anyone reading this file top to bottom.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.core.db import get_db
from relay_api.core.deps import CurrentUser
from relay_api.features.notes import service
from relay_api.features.notes.schemas import NoteCreate, NoteLink, NoteOut, NoteUpdate

router = APIRouter(prefix="/notes", tags=["notes"])


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(
    data: NoteCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NoteOut:
    note = await service.create_note(db, current_user.id, data)
    return NoteOut.model_validate(note, from_attributes=True)


@router.get("", response_model=list[NoteOut])
async def list_notes(
    current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> list[NoteOut]:
    notes = await service.list_notes(db, current_user.id)
    return [NoteOut.model_validate(n, from_attributes=True) for n in notes]


@router.get("/export")
async def export_notes(
    current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> Response:
    notes = await service.list_notes(db, current_user.id)
    markdown = service.export_notes_markdown(notes)
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="relay-notes.md"'},
    )


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: uuid.UUID,
    data: NoteUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NoteOut:
    note = await service.update_note(db, current_user.id, note_id, data)
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    return NoteOut.model_validate(note, from_attributes=True)


@router.post("/{note_id}/links", response_model=NoteOut)
async def add_link(
    note_id: uuid.UUID,
    link: NoteLink,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NoteOut:
    note = await service.add_link(db, current_user.id, note_id, link)
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    return NoteOut.model_validate(note, from_attributes=True)


@router.delete("/{note_id}/links/{link_index}", response_model=NoteOut)
async def remove_link(
    note_id: uuid.UUID,
    link_index: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NoteOut:
    note = await service.remove_link(db, current_user.id, note_id, link_index)
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note or link not found")
    return NoteOut.model_validate(note, from_attributes=True)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    deleted = await service.delete_note(db, current_user.id, note_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")


@router.delete("", response_model=None)
async def delete_all_notes(
    current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict[str, int]:
    deleted_count = await service.delete_all_notes(db, current_user.id)
    return {"deleted_count": deleted_count}
