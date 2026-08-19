"""`features/who_to_ask/service.py`'s own job is collapsing blame into
per-commit touches and dispatching to the right `engine.ranking` strategy
— `engine.code_context` and `connectors.service` are mocked; the ranking
math itself is covered by `tests/differential/test_ranking_strategies.py`.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from relay_api.auth.models import User
from relay_api.engine.code_context.schemas import BlameRange
from relay_api.features.who_to_ask import service

_USER = User(id=uuid.uuid4(), email="dev@example.com", display_name="Dev")
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _blame_range(
    sha: str,
    *,
    author_login: str | None = "octocat",
    author_name: str | None = "Octocat",
    committed_at: datetime = _NOW,
    start: int = 1,
    end: int = 5,
) -> BlameRange:
    return BlameRange(
        starting_line=start,
        ending_line=end,
        commit_sha=sha,
        commit_message="msg",
        commit_url=f"https://github.com/acme/widgets/commit/{sha}",
        committed_at=committed_at,
        author_name=author_name,
        author_login=author_login,
        pull_request=None,
    )


async def _rank_with(ranges: list[BlameRange], strategy: str = "recency"):
    with (
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="tok"),
        ),
        patch.object(service.code_context_service, "get_blame", new=AsyncMock(return_value=ranges)),
    ):
        return await service.rank(
            object(),
            _USER,
            owner="acme",
            repo="widgets",
            ref="main",
            path="x.py",
            strategy=strategy,
        )


async def test_multiple_ranges_from_the_same_commit_count_as_one_touch() -> None:
    ranges = [
        _blame_range("abc", start=1, end=5),
        _blame_range("abc", start=10, end=15),
    ]

    result = await _rank_with(ranges, strategy="frequency")

    assert len(result.people) == 1
    assert result.people[0].touch_count == 1


async def test_distinct_commits_by_the_same_author_accumulate_touches() -> None:
    ranges = [
        _blame_range("abc", committed_at=_NOW - timedelta(days=10)),
        _blame_range("def", committed_at=_NOW),
    ]

    result = await _rank_with(ranges, strategy="frequency")

    assert len(result.people) == 1
    assert result.people[0].touch_count == 2
    assert result.people[0].last_touch_at == _NOW


async def test_commits_with_no_identifiable_author_are_skipped() -> None:
    ranges = [_blame_range("abc", author_login=None, author_name=None)]

    result = await _rank_with(ranges)

    assert result.people == []


async def test_falls_back_to_author_name_when_no_login() -> None:
    ranges = [_blame_range("abc", author_login=None, author_name="Some Bot")]

    result = await _rank_with(ranges)

    assert result.people[0].author == "Some Bot"


async def test_strategy_dispatch_recency_vs_frequency_can_disagree() -> None:
    ranges = [
        _blame_range("recent", author_login="carol", committed_at=_NOW - timedelta(days=1)),
        *[
            _blame_range(f"old-{i}", author_login="dave", committed_at=_NOW - timedelta(days=240))
            for i in range(10)
        ],
    ]

    recency_result = await _rank_with(ranges, strategy="recency")
    frequency_result = await _rank_with(ranges, strategy="frequency")

    assert recency_result.people[0].author == "carol"
    assert frequency_result.people[0].author == "dave"
    assert recency_result.strategy_used == "recency"
    assert frequency_result.strategy_used == "frequency"


async def test_sample_commit_urls_capped_at_two_per_person() -> None:
    ranges = [_blame_range(f"sha-{i}", committed_at=_NOW - timedelta(days=i)) for i in range(5)]

    result = await _rank_with(ranges, strategy="frequency")

    assert len(result.people[0].sample_commit_urls) == 2
