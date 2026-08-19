"""`features/who_to_ask/service.py`'s own job is collapsing blame into
per-commit touches, dispatching to the right `engine.ranking` strategy,
and (per person) correlating a Jira ticket + related Slack discussion via
`engine.correlation` — mocked here the same way `test_archaeology_service.py`
mocks it; the ranking math itself is covered by
`tests/differential/test_ranking_strategies.py`, and `engine.correlation`'s
own logic by `tests/unit/engine/test_correlation.py`.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, AsyncMock, patch

from relay_api.auth.models import User
from relay_api.engine.code_context.schemas import (
    AssociatedPullRequest,
    BlameRange,
    DirectoryBlame,
    FileBlame,
)
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
    message: str = "msg",
    pr: AssociatedPullRequest | None = None,
) -> BlameRange:
    return BlameRange(
        starting_line=start,
        ending_line=end,
        commit_sha=sha,
        commit_message=message,
        commit_url=f"https://github.com/acme/widgets/commit/{sha}",
        committed_at=committed_at,
        author_name=author_name,
        author_login=author_login,
        pull_request=pr,
    )


async def _rank_with(ranges: list[BlameRange], strategy: str = "recency"):
    with (
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="tok"),
        ),
        patch.object(service.code_context_service, "get_blame", new=AsyncMock(return_value=ranges)),
        patch.object(
            service.correlation_service, "get_jira_site_url", new=AsyncMock(return_value=None)
        ),
        patch.object(service.correlation_service, "find_related", new=AsyncMock(return_value=[])),
        patch.object(
            service.correlation_service, "find_similar_jira_issues", new=AsyncMock(return_value=[])
        ),
        patch.object(
            service.correlation_service,
            "find_review_comments_for_pr",
            new=AsyncMock(return_value=[]),
        ),
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


async def test_commits_are_not_capped_and_match_touch_count() -> None:
    # These are already fetched as part of computing the score itself —
    # no reason to truncate the list server-side. Truncating for display
    # is the frontend's job (an expand/collapse), not the API's.
    ranges = [_blame_range(f"sha-{i}", committed_at=_NOW - timedelta(days=i)) for i in range(8)]

    result = await _rank_with(ranges, strategy="frequency")

    assert len(result.people[0].commits) == 8
    assert len(result.people[0].commits) == result.people[0].touch_count


async def test_commits_carry_the_commit_message_not_just_a_bare_url() -> None:
    ranges = [_blame_range("abc", message="Fix retry logic in payment handler\n\nDetails here.")]

    result = await _rank_with(ranges, strategy="frequency")

    commit = result.people[0].commits[0]
    assert commit.message == "Fix retry logic in payment handler"  # first line only
    assert commit.short_sha == "abc"[:7]
    assert commit.url == "https://github.com/acme/widgets/commit/abc"


async def test_commits_are_most_recent_first() -> None:
    ranges = [
        _blame_range("oldest", committed_at=_NOW - timedelta(days=10), message="oldest"),
        _blame_range("newest", committed_at=_NOW, message="newest"),
        _blame_range("middle", committed_at=_NOW - timedelta(days=5), message="middle"),
    ]

    result = await _rank_with(ranges, strategy="frequency")

    assert [c.message for c in result.people[0].commits] == ["newest", "middle", "oldest"]


async def _rank_directory_with(directory_blame: DirectoryBlame, strategy: str = "frequency"):
    with (
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="tok"),
        ),
        patch.object(
            service.code_context_service,
            "get_blame_for_directory",
            new=AsyncMock(return_value=directory_blame),
        ),
        patch.object(
            service.correlation_service, "get_jira_site_url", new=AsyncMock(return_value=None)
        ),
        patch.object(service.correlation_service, "find_related", new=AsyncMock(return_value=[])),
        patch.object(
            service.correlation_service, "find_similar_jira_issues", new=AsyncMock(return_value=[])
        ),
        patch.object(
            service.correlation_service,
            "find_review_comments_for_pr",
            new=AsyncMock(return_value=[]),
        ),
    ):
        return await service.rank(
            object(),
            _USER,
            owner="acme",
            repo="widgets",
            ref="main",
            path="src/payments",
            strategy=strategy,
            target_type="directory",
        )


async def test_directory_mode_counts_a_commit_touching_multiple_files_once() -> None:
    # The correctness-critical case: the same commit ("abc") appears in
    # two different files' blame results because it touched both — it
    # must count as exactly ONE touch for its author, not two.
    directory_blame = DirectoryBlame(
        files=[
            FileBlame(path="src/payments/handler.py", ranges=[_blame_range("abc")]),
            FileBlame(path="src/payments/refunds.py", ranges=[_blame_range("abc")]),
        ],
        files_total=2,
        files_analyzed=2,
        files_skipped=0,
    )

    result = await _rank_directory_with(directory_blame, strategy="frequency")

    assert len(result.people) == 1
    assert result.people[0].touch_count == 1


async def test_directory_mode_pools_distinct_commits_across_files() -> None:
    directory_blame = DirectoryBlame(
        files=[
            FileBlame(path="a.py", ranges=[_blame_range("commit-1", committed_at=_NOW)]),
            FileBlame(
                path="b.py",
                ranges=[_blame_range("commit-2", committed_at=_NOW - timedelta(days=1))],
            ),
        ],
        files_total=2,
        files_analyzed=2,
        files_skipped=0,
    )

    result = await _rank_directory_with(directory_blame, strategy="frequency")

    assert result.people[0].touch_count == 2


async def test_directory_mode_propagates_file_counts_to_response() -> None:
    directory_blame = DirectoryBlame(
        files=[FileBlame(path="a.py", ranges=[_blame_range("abc")])],
        files_total=5,
        files_analyzed=1,
        files_skipped=4,
    )

    result = await _rank_directory_with(directory_blame)

    assert result.files_total == 5
    assert result.files_analyzed == 1
    assert result.files_skipped == 4


async def test_file_mode_still_reports_one_of_one_files() -> None:
    result = await _rank_with([_blame_range("abc")])

    assert result.files_total == 1
    assert result.files_analyzed == 1
    assert result.files_skipped == 0


# --- Jira/Slack correlation (ADR 0012) ---


async def test_ticket_key_comes_from_most_recent_commit_that_has_one() -> None:
    ranges = [
        _blame_range("no-key", message="tweak formatting", committed_at=_NOW),
        _blame_range(
            "has-key", message="REL-42: fix retry logic", committed_at=_NOW - timedelta(days=1)
        ),
    ]

    with (
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="tok"),
        ),
        patch.object(service.code_context_service, "get_blame", new=AsyncMock(return_value=ranges)),
        patch.object(
            service.correlation_service,
            "get_jira_site_url",
            new=AsyncMock(return_value="https://acme.atlassian.net"),
        ),
        patch.object(
            service.correlation_service, "find_related", new=AsyncMock(return_value=[])
        ) as mock_search,
        patch.object(
            service.correlation_service, "find_similar_jira_issues", new=AsyncMock(return_value=[])
        ),
    ):
        result = await service.rank(
            object(),
            _USER,
            owner="acme",
            repo="widgets",
            ref="main",
            path="x.py",
            strategy="frequency",
        )

    assert result.people[0].jira_ticket_key == "REL-42"
    assert result.people[0].jira_ticket_url == "https://acme.atlassian.net/browse/REL-42"
    mock_search.assert_awaited_once()
    assert mock_search.call_args.args[2] == "REL-42"


async def test_ticket_key_falls_back_to_pr_title() -> None:
    pr = AssociatedPullRequest(
        number=1,
        title="REL-99 handle timeout",
        url="https://github.com/acme/widgets/pull/1",
        body="",
    )
    ranges = [_blame_range("abc", message="fix timeout", pr=pr)]

    result = await _rank_with(ranges)

    assert result.people[0].jira_ticket_key == "REL-99"


async def test_no_jira_url_when_jira_not_connected() -> None:
    ranges = [_blame_range("abc", message="REL-42: fix")]

    result = await _rank_with(ranges)

    assert result.people[0].jira_ticket_key == "REL-42"
    assert result.people[0].jira_ticket_url is None


async def test_no_ticket_key_anywhere_leaves_correlation_empty() -> None:
    ranges = [_blame_range("abc", message="tweak formatting")]

    result = await _rank_with(ranges)

    assert result.people[0].jira_ticket_key is None
    assert result.people[0].jira_ticket_url is None
    assert result.people[0].related_slack == []


async def test_only_one_slack_search_fires_per_person_regardless_of_commit_count() -> None:
    # The cost bound that actually matters: many commits, one search.
    ranges = [
        _blame_range(f"sha-{i}", message=f"REL-{i}: work", committed_at=_NOW - timedelta(days=i))
        for i in range(20)
    ]

    with (
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="tok"),
        ),
        patch.object(service.code_context_service, "get_blame", new=AsyncMock(return_value=ranges)),
        patch.object(
            service.correlation_service, "get_jira_site_url", new=AsyncMock(return_value=None)
        ),
        patch.object(
            service.correlation_service, "find_related", new=AsyncMock(return_value=[])
        ) as mock_search,
        patch.object(
            service.correlation_service, "find_similar_jira_issues", new=AsyncMock(return_value=[])
        ),
    ):
        await service.rank(
            object(),
            _USER,
            owner="acme",
            repo="widgets",
            ref="main",
            path="x.py",
            strategy="frequency",
        )

    mock_search.assert_awaited_once()


async def test_ticket_lookback_does_not_reach_past_five_commits() -> None:
    # A ticket key sits on the 6th-most-recent commit — outside the
    # lookback window — so it must NOT be found.
    ranges = [
        _blame_range(f"recent-{i}", message="no key", committed_at=_NOW - timedelta(days=i))
        for i in range(5)
    ] + [_blame_range("too-old", message="REL-1: old work", committed_at=_NOW - timedelta(days=5))]

    result = await _rank_with(ranges)

    assert result.people[0].jira_ticket_key is None


async def test_similar_issues_populate_when_ticket_key_found() -> None:
    ranges = [_blame_range("abc", message="REL-42: fix retry logic")]
    similar = service.correlation_service.RelatedItem(
        source="jira",
        title="Similar issue",
        url="https://acme.atlassian.net/browse/REL-7",
        excerpt="a similar past issue",
        occurred_at=_NOW,
    )

    with (
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="tok"),
        ),
        patch.object(service.code_context_service, "get_blame", new=AsyncMock(return_value=ranges)),
        patch.object(
            service.correlation_service, "get_jira_site_url", new=AsyncMock(return_value=None)
        ),
        patch.object(service.correlation_service, "find_related", new=AsyncMock(return_value=[])),
        patch.object(
            service.correlation_service,
            "find_similar_jira_issues",
            new=AsyncMock(return_value=[similar]),
        ) as mock_similar,
    ):
        result = await service.rank(
            object(),
            _USER,
            owner="acme",
            repo="widgets",
            ref="main",
            path="x.py",
            strategy="frequency",
        )

    assert len(result.people[0].similar_issues) == 1
    assert result.people[0].similar_issues[0].url == "https://acme.atlassian.net/browse/REL-7"
    mock_similar.assert_awaited_once()


async def test_similar_issues_lookup_skipped_when_no_ticket_key() -> None:
    ranges = [_blame_range("abc", message="tweak formatting")]

    with (
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="tok"),
        ),
        patch.object(service.code_context_service, "get_blame", new=AsyncMock(return_value=ranges)),
        patch.object(
            service.correlation_service, "get_jira_site_url", new=AsyncMock(return_value=None)
        ),
        patch.object(service.correlation_service, "find_related", new=AsyncMock(return_value=[])),
        patch.object(
            service.correlation_service, "find_similar_jira_issues", new=AsyncMock(return_value=[])
        ) as mock_similar,
    ):
        result = await service.rank(
            object(),
            _USER,
            owner="acme",
            repo="widgets",
            ref="main",
            path="x.py",
            strategy="frequency",
        )

    assert result.people[0].similar_issues == []
    mock_similar.assert_not_awaited()


# --- Reviewers as touches (ADR 0016) ---


async def test_a_review_only_contributor_is_ranked_with_no_commits_and_nonempty_reviews() -> None:
    pr = AssociatedPullRequest(
        number=7,
        title="REL-42 fix retry logic",
        url="https://github.com/acme/widgets/pull/7",
        body="",
    )
    ranges = [_blame_range("abc", author_login="carol", pr=pr)]
    review = service.correlation_service.ReviewItem(
        author="dave",  # never committed — only reviewed carol's PR
        excerpt="One nit, otherwise fine.",
        url="https://github.com/acme/widgets/pull/7#pullrequestreview-1",
        occurred_at=_NOW,
        state="APPROVED",
    )

    with (
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="tok"),
        ),
        patch.object(service.code_context_service, "get_blame", new=AsyncMock(return_value=ranges)),
        patch.object(
            service.correlation_service, "get_jira_site_url", new=AsyncMock(return_value=None)
        ),
        patch.object(service.correlation_service, "find_related", new=AsyncMock(return_value=[])),
        patch.object(
            service.correlation_service, "find_similar_jira_issues", new=AsyncMock(return_value=[])
        ),
        patch.object(
            service.correlation_service,
            "find_review_comments_for_pr",
            new=AsyncMock(return_value=[review]),
        ),
    ):
        result = await service.rank(
            object(),
            _USER,
            owner="acme",
            repo="widgets",
            ref="main",
            path="x.py",
            strategy="frequency",
        )

    people_by_author = {p.author: p for p in result.people}
    assert "dave" in people_by_author
    dave = people_by_author["dave"]
    assert dave.commits == []
    assert len(dave.reviews) == 1
    assert dave.reviews[0].pr_number == 7
    assert dave.reviews[0].pr_title == "REL-42 fix retry logic"
    assert dave.touch_count == 1

    carol = people_by_author["carol"]
    assert len(carol.commits) == 1
    assert carol.reviews == []


async def test_review_comments_fetched_once_per_distinct_pr_not_per_commit() -> None:
    # Two commits, same PR — the review lookup must fire once, not twice.
    pr = AssociatedPullRequest(
        number=7,
        title="REL-42 fix retry logic",
        url="https://github.com/acme/widgets/pull/7",
        body="",
    )
    ranges = [
        _blame_range("abc", author_login="carol", pr=pr, committed_at=_NOW - timedelta(days=1)),
        _blame_range("def", author_login="carol", pr=pr, committed_at=_NOW),
    ]

    with (
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="tok"),
        ),
        patch.object(service.code_context_service, "get_blame", new=AsyncMock(return_value=ranges)),
        patch.object(
            service.correlation_service, "get_jira_site_url", new=AsyncMock(return_value=None)
        ),
        patch.object(service.correlation_service, "find_related", new=AsyncMock(return_value=[])),
        patch.object(
            service.correlation_service, "find_similar_jira_issues", new=AsyncMock(return_value=[])
        ),
        patch.object(
            service.correlation_service,
            "find_review_comments_for_pr",
            new=AsyncMock(return_value=[]),
        ) as mock_reviews,
    ):
        await service.rank(
            object(),
            _USER,
            owner="acme",
            repo="widgets",
            ref="main",
            path="x.py",
            strategy="frequency",
        )

    mock_reviews.assert_awaited_once_with(ANY, _USER.id, "acme", "widgets", 7)


async def test_no_reviews_when_no_commit_has_an_associated_pr() -> None:
    ranges = [_blame_range("abc", author_login="carol")]

    result = await _rank_with(ranges, strategy="frequency")

    assert result.people[0].reviews == []
