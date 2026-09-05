"""The common shape every connector normalizes into before it enters the
engine. This is the actual "one engine" contract (ADR 0005) — GitHub PRs,
Slack messages, and Jira issues are structurally different, but by the time
they're a `NormalizedItem` they're interchangeable rows the rest of the
engine (`indexing`, and `ranking` in Phase 2) never needs provider-specific
logic to handle.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

Source = Literal["github", "slack", "jira", "notes"]
SourceType = Literal[
    "pull_request", "commit", "message", "issue", "review_comment", "note", "decision_doc"
]
"""`"review_comment"` covers both a PR's top-level review verdicts
(APPROVED/CHANGES_REQUESTED/COMMENTED, with a body) and inline code
comments — one type, not two, since both are "commentary during code
review" and every downstream consumer (`engine.correlation.
find_review_comments_for_pr`) treats them identically. See ADR 0016.

`"notes"` is the one source here that isn't a connector — `features.notes`
writes it directly (via the same `upsert_items`/`index_items` every
connector uses), synchronously on save rather than on a poll cadence,
since there's nothing external to poll. See ADR 0021."""


@dataclass(frozen=True)
class NormalizedItem:
    source: Source
    source_type: SourceType
    external_id: str
    """Id from the provider's own API — the dedupe key within (user, source, source_type)."""
    title: str
    body: str
    url: str
    author: str | None
    occurred_at: datetime
    extra: dict[str, Any] = field(default_factory=dict)
    """Small bag of source-specific display fields (repo name, channel name, etc.) —
    never queried on, just carried through for the UI. Anything that needs to be
    queried on belongs as a first-class column, not in here."""
