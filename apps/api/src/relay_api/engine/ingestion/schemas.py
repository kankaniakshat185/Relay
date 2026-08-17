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

Source = Literal["github", "slack", "jira"]
SourceType = Literal["pull_request", "commit", "message", "issue"]


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
