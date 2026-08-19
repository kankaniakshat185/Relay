"""Two competing scoring strategies over the same `Touch` data — the
concrete instance of plan.md §6's differential testing strategy: pure
functions, no I/O, compared against a shared fixture set in
`tests/differential/test_ranking_strategies.py` rather than picking one
"correct" answer up front.

`features/who_to_ask` is the first (only, for now) caller: given who
touched a file and when, which person is most worth asking? Recency and
frequency genuinely disagree on this — someone who wrote most of a file
two years ago and hasn't touched it since scores high on frequency, low on
recency; someone who just fixed one bug in it yesterday is the reverse.
Neither answer is wrong, which is exactly why this is differential-tested
rather than collapsed into one "best" score like `engine/indexing`'s fixed
0.4/0.6 hybrid weighting.
"""

from collections import defaultdict
from datetime import datetime

from relay_api.engine.ranking.schemas import RankedPerson, Touch

_DEFAULT_HALF_LIFE_DAYS = 30.0


def _group_by_author(touches: list[Touch]) -> dict[str, list[Touch]]:
    groups: dict[str, list[Touch]] = defaultdict(list)
    for touch in touches:
        groups[touch.author].append(touch)
    return groups


def rank_by_recency(
    touches: list[Touch], *, now: datetime, half_life_days: float = _DEFAULT_HALF_LIFE_DAYS
) -> list[RankedPerson]:
    """Each touch contributes `2 ** (-age_days / half_life_days)` — a touch
    from today counts fully, one from `half_life_days` ago counts half as
    much, and so on. Touches per author sum, so someone who's both recent
    *and* frequent still ranks above someone merely recent."""
    people = []
    for author, author_touches in _group_by_author(touches).items():
        score = sum(
            2 ** (-((now - t.occurred_at).total_seconds() / 86400) / half_life_days)
            for t in author_touches
        )
        people.append(
            RankedPerson(
                author=author,
                score=score,
                touch_count=len(author_touches),
                last_touch_at=max(t.occurred_at for t in author_touches),
            )
        )
    return sorted(people, key=lambda p: p.score, reverse=True)


def rank_by_frequency(touches: list[Touch]) -> list[RankedPerson]:
    """Raw touch count, no time decay — someone who touched a file 50 times
    two years ago still outranks someone with 2 touches last week. Ties
    (equal counts) broken by most recent touch."""
    people = []
    for author, author_touches in _group_by_author(touches).items():
        last_touch_at = max(t.occurred_at for t in author_touches)
        people.append(
            RankedPerson(
                author=author,
                score=float(len(author_touches)),
                touch_count=len(author_touches),
                last_touch_at=last_touch_at,
            )
        )
    return sorted(people, key=lambda p: (p.score, p.last_touch_at), reverse=True)
