"""`features/archaeology/service.py` orchestrates engine calls it doesn't
own — `engine.code_context` and `engine.correlation` are both mocked
here; this tests the collapsing/timeline-building logic that's actually
this feature's own. `engine.correlation`'s own extraction/URL/search
logic has its own unit tests (`tests/unit/engine/test_correlation.py`) —
`extract_ticket_key` is a pure function, so it's exercised for real here
rather than mocked, same as before this logic moved into engine/."""

import uuid
from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock, patch

from relay_api.auth.models import User
from relay_api.engine.code_context.schemas import (
    AssociatedPullRequest,
    BlameRange,
    DirectoryBlame,
    FileBlame,
)
from relay_api.features.archaeology import service

_USER = User(id=uuid.uuid4(), email="dev@example.com", display_name="Dev")


def _blame_range(
    sha: str,
    *,
    start: int = 1,
    end: int = 5,
    message: str = "Fix bug",
    committed_at: datetime = datetime(2026, 1, 1, tzinfo=UTC),
    pr: AssociatedPullRequest | None = None,
) -> BlameRange:
    return BlameRange(
        starting_line=start,
        ending_line=end,
        commit_sha=sha,
        commit_message=message,
        commit_url=f"https://github.com/acme/widgets/commit/{sha}",
        committed_at=committed_at,
        author_name="Octocat",
        author_login="octocat",
        pull_request=pr,
    )


async def test_trace_collapses_multiple_ranges_from_the_same_commit() -> None:
    ranges = [_blame_range("abc", start=1, end=5), _blame_range("abc", start=10, end=15)]

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
    ):
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    assert len(result.timeline) == 1
    assert len(result.timeline[0].line_ranges) == 2


async def test_trace_orders_commits_most_recent_first() -> None:
    ranges = [
        _blame_range("old", committed_at=datetime(2025, 1, 1, tzinfo=UTC)),
        _blame_range("new", committed_at=datetime(2026, 1, 1, tzinfo=UTC)),
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
    ):
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    assert [c.sha for c in result.timeline] == ["new", "old"]


async def test_trace_extracts_ticket_key_from_commit_message() -> None:
    ranges = [_blame_range("abc", message="REL-42: fix retry logic")]

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
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    entry = result.timeline[0]
    assert entry.jira_ticket_key == "REL-42"
    assert entry.jira_ticket_url == "https://acme.atlassian.net/browse/REL-42"
    mock_search.assert_awaited_once()
    assert mock_search.call_args.args[2] == "REL-42"  # searched Slack using the ticket key


async def test_trace_populates_similar_issues_when_ticket_key_found() -> None:
    ranges = [_blame_range("abc", message="REL-42: fix retry logic")]
    similar = service.correlation_service.RelatedItem(
        source="jira",
        title="Similar issue",
        url="https://acme.atlassian.net/browse/REL-7",
        excerpt="a similar past issue",
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
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
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    entry = result.timeline[0]
    assert len(entry.similar_issues) == 1
    assert entry.similar_issues[0].url == "https://acme.atlassian.net/browse/REL-7"
    mock_similar.assert_awaited_once_with(ANY, _USER.id, "REL-42")


async def test_trace_skips_similar_issues_lookup_when_no_ticket_key() -> None:
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
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    assert result.timeline[0].similar_issues == []
    mock_similar.assert_not_awaited()


async def test_trace_falls_back_to_pr_title_for_ticket_key() -> None:
    pr = AssociatedPullRequest(
        number=1,
        title="REL-99 handle timeout",
        url="https://github.com/acme/widgets/pull/1",
        body="",
    )
    ranges = [_blame_range("abc", message="fix timeout", pr=pr)]

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
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    assert result.timeline[0].jira_ticket_key == "REL-99"
    assert result.timeline[0].jira_ticket_url is None  # no Jira connected


async def test_trace_populates_review_comments_for_a_commits_pr() -> None:
    pr = AssociatedPullRequest(
        number=7,
        title="REL-42 fix retry logic",
        url="https://github.com/acme/widgets/pull/7",
        body="",
    )
    ranges = [_blame_range("abc", message="REL-42: fix retry logic", pr=pr)]
    review = service.correlation_service.ReviewItem(
        author="reviewer",
        excerpt="Looks good, one nit.",
        url="https://github.com/acme/widgets/pull/7#pullrequestreview-1",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
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
        ) as mock_reviews,
    ):
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    entry = result.timeline[0]
    assert len(entry.review_comments) == 1
    assert entry.review_comments[0].author == "reviewer"
    assert entry.pull_request is not None
    assert entry.pull_request.has_unresolved_review is False
    mock_reviews.assert_awaited_once_with(ANY, _USER.id, "acme", "widgets", 7)


async def test_trace_flags_a_pr_whose_review_history_ends_on_changes_requested() -> None:
    pr = AssociatedPullRequest(
        number=7,
        title="REL-42 fix retry logic",
        url="https://github.com/acme/widgets/pull/7",
        body="",
    )
    ranges = [_blame_range("abc", message="REL-42: fix retry logic", pr=pr)]
    reviews = [
        service.correlation_service.ReviewItem(
            author="reviewer",
            excerpt="Please address this before merging.",
            url="https://github.com/acme/widgets/pull/7#pullrequestreview-1",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            state="CHANGES_REQUESTED",
        )
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
            new=AsyncMock(return_value=reviews),
        ),
    ):
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    assert result.timeline[0].pull_request is not None
    assert result.timeline[0].pull_request.has_unresolved_review is True


async def test_trace_skips_review_lookup_for_commits_with_no_pr() -> None:
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
            service.correlation_service,
            "find_review_comments_for_pr",
            new=AsyncMock(return_value=[]),
        ) as mock_reviews,
    ):
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    assert result.timeline[0].review_comments == []
    assert result.timeline[0].pull_request is None
    mock_reviews.assert_not_awaited()


async def test_trace_with_no_ticket_key_and_no_pr_skips_slack_search() -> None:
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
        patch.object(
            service.correlation_service, "find_related", new=AsyncMock(return_value=[])
        ) as mock_search,
    ):
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    assert result.timeline[0].related_slack == []
    # find_related_slack is still called (it's the one that decides an
    # empty query short-circuits — see tests/unit/engine/test_correlation.py),
    # but with a None query since there's nothing to search for.
    assert mock_search.call_args.args[2] is None


async def test_trace_directory_mode_collapses_a_commit_touching_multiple_files() -> None:
    # The correctness-critical case: a single commit ("abc") touched two
    # different files under the directory. It must produce ONE timeline
    # entry listing both files, not two entries.
    directory_blame = DirectoryBlame(
        files=[
            FileBlame(path="src/payments/handler.py", ranges=[_blame_range("abc", start=1, end=5)]),
            FileBlame(
                path="src/payments/refunds.py", ranges=[_blame_range("abc", start=10, end=15)]
            ),
        ],
        files_total=2,
        files_analyzed=2,
        files_skipped=0,
    )

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
    ):
        result = await service.trace(
            object(),
            _USER,
            owner="acme",
            repo="widgets",
            ref="main",
            path="src/payments",
            target_type="directory",
        )

    assert len(result.timeline) == 1
    assert sorted(result.timeline[0].files_touched) == [
        "src/payments/handler.py",
        "src/payments/refunds.py",
    ]
    assert result.timeline[0].line_ranges == []  # not meaningful across multiple files
    assert result.files_total == 2
    assert result.files_analyzed == 2
    assert result.files_skipped == 0


async def test_trace_directory_mode_propagates_skipped_file_count() -> None:
    directory_blame = DirectoryBlame(
        files=[FileBlame(path="a.py", ranges=[_blame_range("abc")])],
        files_total=3,
        files_analyzed=1,
        files_skipped=2,
    )

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
    ):
        result = await service.trace(
            object(),
            _USER,
            owner="acme",
            repo="widgets",
            ref="main",
            path="src",
            target_type="directory",
        )

    assert result.files_total == 3
    assert result.files_analyzed == 1
    assert result.files_skipped == 2


async def test_trace_file_mode_still_reports_one_of_one_files() -> None:
    ranges = [_blame_range("abc")]

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
    ):
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    assert result.files_total == 1
    assert result.files_analyzed == 1
    assert result.files_skipped == 0
    assert result.timeline[0].files_touched == ["x.py"]
