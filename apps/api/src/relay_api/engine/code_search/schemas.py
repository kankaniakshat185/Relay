"""Shapes `engine/code_search` returns to its two callers
(`features/archaeology`, `features/who_to_ask`) — plain dataclasses, not
Pydantic, same convention as `engine/code_context/schemas.py`: neither
crosses the HTTP boundary directly, each feature maps it into its own
response schema."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class FileMatch:
    """One candidate commit or PR a text search resolved, plus the files
    it actually touched — a starting point for the ticket/PR-first entry
    point (ADR 0015), not itself something to blame. The frontend still
    calls the normal `trace`/`rank` endpoint once a file is picked from
    `files`."""

    kind: Literal["commit", "pull_request"]
    repo: str
    """`"owner/name"` — split by the caller if it needs the parts."""
    title: str
    url: str
    occurred_at: datetime
    files: list[str]
    sha: str | None = None
    """Set when `kind == "commit"`."""
    pr_number: int | None = None
    """Set when `kind == "pull_request"`."""
