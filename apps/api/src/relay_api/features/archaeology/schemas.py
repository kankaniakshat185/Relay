from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from relay_api.engine.timeline.schemas import LineRange, PullRequestRef, RelatedItem, ReviewComment
from relay_api.engine.timeline.schemas import TimelineEntry as CommitEntry
from relay_api.engine.timeline.schemas import TimelineResult as ArchaeologyResponse

__all__ = [
    "ArchaeologyRequest",
    "ArchaeologyResponse",
    "CommitEntry",
    "DirectoryEntry",
    "FileSearchMatch",
    "LineRange",
    "PullRequestRef",
    "RelatedItem",
    "RepoOption",
    "ReviewComment",
]
"""`LineRange`/`PullRequestRef`/`RelatedItem`/`ReviewComment`/`CommitEntry`/
`ArchaeologyResponse` all moved to `engine/timeline/schemas.py` (renamed
`CommitEntry`→`TimelineEntry`, `ArchaeologyResponse`→`TimelineResult`
there) once `features/incident_correlation` needed the exact same
correlated-timeline shape — re-exported here under their original names
so this module's own wire format and every existing import of it are
unchanged. See `engine/timeline/service.py`'s docstring."""


class RepoOption(BaseModel):
    owner: str
    name: str
    full_name: str
    default_branch: str


class DirectoryEntry(BaseModel):
    name: str
    path: str
    type: Literal["file", "dir"]


class ArchaeologyRequest(BaseModel):
    owner: str
    repo: str
    ref: str
    """Branch/tag/sha to blame at — the frontend always sends the repo's
    `default_branch` from the `/repos` response, so this is required
    rather than defaulted here."""
    path: str
    target_type: Literal["file", "directory"] = "file"
    """`path` is a single file (existing behavior) or a directory — every
    file under it gets blamed and merged into one timeline. Set by the
    picker, which already knows which one was clicked; the backend never
    has to guess."""


class FileSearchMatch(BaseModel):
    """One candidate commit or PR the `/search` endpoint resolved — see
    `engine.code_search.service.find_files_for_query`. Picking a file
    from `files` feeds the existing `/trace` request the same way the
    repo-browse picker already does; this is just a second way to arrive
    at that same file, not a new response shape downstream."""

    kind: Literal["commit", "pull_request"]
    repo: str
    title: str
    url: str
    occurred_at: datetime
    files: list[str]
    sha: str | None
    pr_number: int | None
