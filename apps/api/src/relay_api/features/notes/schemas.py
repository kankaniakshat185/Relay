from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

LinkedSource = Literal["github", "slack", "jira"]
"""What a note can link to via the "annotate this" flow (Search,
Archaeology, Who Should I Ask) — deliberately a subset of
`engine.ingestion.schemas.Source`, which also includes `"notes"` itself;
a note linking to another note isn't a case this feature supports."""


class NoteLink(BaseModel):
    """One reference to an existing GitHub/Slack/Jira item — denormalized
    (source/url/title snapshotted, not a foreign key), same reasoning as
    the rest of this feature's mirroring: the linked item can be
    re-ingested, change title, or fall out of the connector's fetch
    window, and a note should still show what it pointed at when the
    link was made, not go stale or break."""

    source: LinkedSource
    url: str
    title: str


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    links: list[NoteLink] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    """All fields optional — a `PATCH`, not a full replace. `links` is
    intentionally NOT editable here — adding one goes through the
    dedicated `POST /{note_id}/links` endpoint (the "attach to an
    existing note" flow), which reuses real ingested data rather than
    letting arbitrary URLs/titles be typed in by hand."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = None
    tags: list[str] | None = None


class NoteOut(BaseModel):
    id: UUID
    title: str
    body: str
    tags: list[str]
    links: list[NoteLink]
    created_at: datetime
    updated_at: datetime
