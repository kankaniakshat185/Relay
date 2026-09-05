from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DecisionDebtRequest(BaseModel):
    owner: str
    repo: str
    min_discussion_items: int = Field(default=2, ge=1, le=20)
    """How much correlated Slack/Jira discussion a PR needs before its
    absence of a decision doc counts as "debt" — a threshold, not a
    guess: a PR with one passing Slack mention isn't evidence of an
    undocumented decision, a PR with real back-and-forth is."""
    inactive_after_days: int = Field(default=180, ge=1, le=730)
    """How long since a PR's author last showed up as a commit author on
    ANY of this user's connected repos before they're flagged as possibly
    gone — raises the stakes of a flagged PR having no documentation
    trail at all."""


class RelatedItem(BaseModel):
    """`engine.correlation.schemas.RelatedItem` (a plain dataclass — see
    that module's own docstring for why it never crosses the HTTP
    boundary directly) shaped for the wire, same `**vars()` conversion
    convention `engine/timeline` already uses for the same reason."""

    source: Literal["slack", "jira", "github"]
    title: str
    url: str
    excerpt: str
    occurred_at: datetime


class FlaggedPullRequest(BaseModel):
    number: int
    title: str
    url: str
    author: str | None
    author_inactive: bool
    """True only when `author` has a commit history on a connected repo
    that's genuinely gone stale (older than `inactive_after_days`).
    `False` — not an error — when `author` is `None` or has no commit
    history to check at all; insufficient signal to claim inactivity is
    not the same as evidence of activity."""
    discussion: list[RelatedItem]
    """The correlated Slack/Jira discussion that got this PR flagged —
    evidence for why, not a full transcript (capped, see
    `features/decision_debt/service.py`'s `_DISCUSSION_LIMIT`)."""


class DecisionDebtResponse(BaseModel):
    flagged: list[FlaggedPullRequest]
    prs_scanned: int
    decision_docs_found: int
    """How many decision docs exist for this repo at all, independent of
    `flagged` — context for reading it: many flagged PRs alongside zero
    decision docs found reads very differently from many flagged PRs
    despite an active decision-doc folder existing."""
