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


class LineRange(BaseModel):
    start: int
    end: int


class PullRequestRef(BaseModel):
    number: int
    title: str
    url: str


class RelatedSlackMessage(BaseModel):
    title: str
    url: str
    excerpt: str
    occurred_at: datetime


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
    here with several ranges, not once per range."""
    pull_request: PullRequestRef | None
    jira_ticket_key: str | None
    jira_ticket_url: str | None
    related_slack: list[RelatedSlackMessage]


class ArchaeologyResponse(BaseModel):
    timeline: list[CommitEntry]
    """Most recently committed first."""
