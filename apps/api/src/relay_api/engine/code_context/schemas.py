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


@dataclass(frozen=True)
class FileBlame:
    path: str
    ranges: list[BlameRange]


@dataclass(frozen=True)
class DirectoryBlame:
    """Result of blaming an explicit set of files — a directory's
    contents (`service.get_blame_for_directory`) or a pull request's
    changed files (`service.get_blame_for_pull_request`); both resolve to
    a plain path list and share the same concurrent-blame-with-skip
    machinery (`service._blame_paths`), so this shape is generic over
    either source, not directory-specific despite the name. `files_total`
    counts the paths resolved before any cap or per-file failure; the gap
    between it and `files_analyzed` (`files_skipped`) is meant to be shown
    to the user, not hidden."""

    files: list[FileBlame]
    files_total: int
    files_analyzed: int
    files_skipped: int
