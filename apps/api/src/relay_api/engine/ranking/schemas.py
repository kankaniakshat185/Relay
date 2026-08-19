"""Shared shapes for `engine/ranking`'s scoring strategies. Deliberately
generic — a `Touch` is "someone touched something at some time," not tied
to git/blame specifically, so this stays reusable if a future feature
needs the same recency/frequency tradeoff over a different kind of touch
(e.g. Slack message authorship)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Touch:
    author: str
    occurred_at: datetime


@dataclass(frozen=True)
class RankedPerson:
    author: str
    score: float
    touch_count: int
    last_touch_at: datetime
