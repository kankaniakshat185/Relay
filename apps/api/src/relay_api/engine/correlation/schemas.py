"""Shapes `engine/correlation` returns to its callers
(`features/archaeology`, `features/who_to_ask`) — a plain dataclass, not
Pydantic, same convention as `engine/code_context/schemas.py`: this never
crosses the HTTP boundary directly, each feature maps it into its own
response schema via `**vars()`."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class RelatedItem:
    """A retrieved item related to whatever the caller was correlating
    against — a Slack message discussing a ticket, a past Jira issue
    similar to the current one, or (ADR 0027) a decision doc correlated
    against a PR. Deliberately source-agnostic: the shape was always the
    same regardless (Build 1, ADR 0014) — only the query and which
    `sources`/`source_types` `engine.indexing.service.search` was scoped
    to differed, which is a caller concern, not a shape concern."""

    source: Literal["slack", "jira", "github"]
    title: str
    url: str
    excerpt: str
    occurred_at: datetime


@dataclass(frozen=True)
class ReviewItem:
    """One piece of code-review commentary on a PR — either a top-level
    review verdict (`state` set to APPROVED/CHANGES_REQUESTED/COMMENTED)
    or an inline code comment (`state` is `None`). Both come from the
    same ingested `"review_comment"` source_type (ADR 0016) — one shape,
    not two, since both are "commentary during code review.\""""

    author: str | None
    excerpt: str
    url: str
    occurred_at: datetime
    state: str | None
