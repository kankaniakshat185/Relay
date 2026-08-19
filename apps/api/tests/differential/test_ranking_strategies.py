"""Differential test for `engine/ranking` (plan.md §6) — the one module
scoped for this kind of test. Recency-weighted and frequency-weighted
scoring are two legitimate, disagreeing answers to "who should I ask,"
not a bug to be fixed by picking a winner. This asserts where they agree
and documents, with a concrete fixture, exactly where and why they
diverge.
"""

from datetime import UTC, datetime, timedelta

from relay_api.engine.ranking.schemas import Touch
from relay_api.engine.ranking.strategies import rank_by_frequency, rank_by_recency

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_both_strategies_agree_when_one_author_dominates_both_axes() -> None:
    # Alice touched the file recently AND far more often than Bob — no
    # tension between the two signals, so both strategies should rank her
    # first.
    touches = [
        Touch(author="alice", occurred_at=_NOW - timedelta(days=1)),
        Touch(author="alice", occurred_at=_NOW - timedelta(days=10)),
        Touch(author="alice", occurred_at=_NOW - timedelta(days=20)),
        Touch(author="bob", occurred_at=_NOW - timedelta(days=200)),
    ]

    recency_ranked = rank_by_recency(touches, now=_NOW)
    frequency_ranked = rank_by_frequency(touches)

    assert recency_ranked[0].author == "alice"
    assert frequency_ranked[0].author == "alice"


def test_strategies_diverge_on_recent_but_rare_vs_old_but_frequent() -> None:
    # Carol fixed one bug yesterday. Dave wrote most of the file in a burst
    # eight months ago and hasn't touched it since. Recency should favor
    # Carol (her one touch is barely decayed); frequency should favor Dave
    # (10 touches beats 1, no matter how old). This is the actual case the
    # two strategies exist to handle differently — the fixture documents
    # the disagreement rather than treating it as a discrepancy to fix.
    touches = [
        Touch(author="carol", occurred_at=_NOW - timedelta(days=1)),
        *[Touch(author="dave", occurred_at=_NOW - timedelta(days=240)) for _ in range(10)],
    ]

    recency_ranked = rank_by_recency(touches, now=_NOW, half_life_days=30)
    frequency_ranked = rank_by_frequency(touches)

    assert recency_ranked[0].author == "carol"
    assert frequency_ranked[0].author == "dave"


def test_recency_score_decays_by_half_at_the_half_life() -> None:
    touch_today = [Touch(author="today", occurred_at=_NOW)]
    touch_one_half_life_ago = [Touch(author="aged", occurred_at=_NOW - timedelta(days=30))]

    today_score = rank_by_recency(touch_today, now=_NOW, half_life_days=30)[0].score
    aged_score = rank_by_recency(touch_one_half_life_ago, now=_NOW, half_life_days=30)[0].score

    assert today_score == 1.0
    assert aged_score == 0.5


def test_frequency_ties_break_by_more_recent_touch() -> None:
    touches = [
        Touch(author="earlier", occurred_at=_NOW - timedelta(days=100)),
        Touch(author="later", occurred_at=_NOW - timedelta(days=1)),
    ]

    ranked = rank_by_frequency(touches)

    assert ranked[0].author == "later"
    assert ranked[0].touch_count == ranked[1].touch_count == 1


def test_touch_count_and_last_touch_at_are_correct_regardless_of_strategy() -> None:
    touches = [
        Touch(author="alice", occurred_at=_NOW - timedelta(days=5)),
        Touch(author="alice", occurred_at=_NOW - timedelta(days=1)),
    ]

    for ranked in (rank_by_recency(touches, now=_NOW), rank_by_frequency(touches)):
        assert ranked[0].touch_count == 2
        assert ranked[0].last_touch_at == _NOW - timedelta(days=1)
