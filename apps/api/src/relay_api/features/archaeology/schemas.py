from datetime import datetime
from typing import Literal

from pydantic import BaseModel


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


class LineRange(BaseModel):
    start: int
    end: int


class PullRequestRef(BaseModel):
    number: int
    title: str
    url: str
    has_unresolved_review: bool = False
    """True when this PR's review history, read literally, ends on a
    CHANGES_REQUESTED with no later APPROVED — a heuristic, not ground
    truth (see `engine.correlation.service.has_unresolved_concerns`)."""


class RelatedItem(BaseModel):
    source: Literal["slack", "jira"]
    title: str
    url: str
    excerpt: str
    occurred_at: datetime


class ReviewComment(BaseModel):
    """One piece of code-review commentary — a top-level review verdict
    (`state` set) or an inline code comment (`state` is `None`)."""

    author: str | None
    excerpt: str
    url: str
    occurred_at: datetime
    state: str | None


class CommitEntry(BaseModel):
    sha: str
    short_sha: str
    message: str
    author: str | None
    committed_at: datetime
    url: str
    line_ranges: list[LineRange]
    """Every blame range this commit is still responsible for in the
    requested file — a commit that touched most of a file shows up once
    here with several ranges, not once per range. Empty in directory mode
    (see `files_touched`) — flattening line ranges across several
    different files isn't a meaningful thing to show."""
    files_touched: list[str]
    """`[path]` in file mode. In directory mode, every file under the
    directory this commit touched — a PR that changed 5 files in the
    module is one timeline entry with 5 entries here, not 5 entries."""
    pull_request: PullRequestRef | None
    jira_ticket_key: str | None
    jira_ticket_url: str | None
    related_slack: list[RelatedItem]
    similar_issues: list[RelatedItem]
    """Other Jira issues semantically similar to `jira_ticket_key`'s own
    content — empty whenever no ticket key was found, same as
    `related_slack`."""
    review_comments: list[ReviewComment]
    """This commit's PR's code-review commentary, oldest first — empty
    when the commit has no associated PR, or the PR's reviews were never
    ingested (see `_REVIEW_FETCH_LIMIT`, ADR 0016)."""


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


class ArchaeologyResponse(BaseModel):
    timeline: list[CommitEntry]
    """Most recently committed first."""
    files_total: int = 1
    files_analyzed: int = 1
    files_skipped: int = 0
    """All three are `1`/`1`/`0` in file mode — directory mode is the only
    case where they vary, but they're always present so the frontend
    doesn't need a mode branch just to read them."""
