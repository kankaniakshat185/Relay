"""Shapes `engine/code_context` returns to its two callers
(`features/archaeology`, `features/who_to_ask`) — plain dataclasses, not
Pydantic: these never cross the HTTP boundary directly, each feature maps
them into its own response schema."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class RepoSummary:
    owner: str
    name: str
    full_name: str
    default_branch: str


@dataclass(frozen=True)
class DirectoryEntry:
    name: str
    path: str
    type: Literal["file", "dir"]


@dataclass(frozen=True)
class AssociatedPullRequest:
    number: int
    title: str
    url: str
    body: str


@dataclass(frozen=True)
class BlameRange:
    starting_line: int
    ending_line: int
    commit_sha: str
    commit_message: str
    commit_url: str
    committed_at: datetime
    author_name: str | None
    author_login: str | None
    pull_request: AssociatedPullRequest | None = field(default=None)
