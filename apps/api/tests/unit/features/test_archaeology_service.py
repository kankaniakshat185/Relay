"""`features/archaeology/service.py` orchestrates engine calls it doesn't
own — `engine.code_context`, `engine.indexing.search`, `connectors.service`
are all mocked here; this tests the collapsing/ticket-extraction/timeline
logic that's actually this feature's own."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from relay_api.auth.models import User
from relay_api.connectors.models import ConnectorCredential
from relay_api.engine.code_context.schemas import AssociatedPullRequest, BlameRange
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
        patch.object(service.connector_service, "get_credential", new=AsyncMock(return_value=None)),
        patch.object(service, "engine_search", new=AsyncMock(return_value=[])),
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
        patch.object(service.connector_service, "get_credential", new=AsyncMock(return_value=None)),
        patch.object(service, "engine_search", new=AsyncMock(return_value=[])),
    ):
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    assert [c.sha for c in result.timeline] == ["new", "old"]


async def test_trace_extracts_ticket_key_from_commit_message() -> None:
    ranges = [_blame_range("abc", message="REL-42: fix retry logic")]

    jira_credential = ConnectorCredential(
        provider="jira",
        access_token_encrypted="x",
        scope="read:jira-work",
        external_account_id="cloud-1",
        external_account_label="https://acme.atlassian.net",
    )

    with (
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="tok"),
        ),
        patch.object(service.code_context_service, "get_blame", new=AsyncMock(return_value=ranges)),
        patch.object(
            service.connector_service, "get_credential", new=AsyncMock(return_value=jira_credential)
        ),
        patch.object(service, "engine_search", new=AsyncMock(return_value=[])) as mock_search,
    ):
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    entry = result.timeline[0]
    assert entry.jira_ticket_key == "REL-42"
    assert entry.jira_ticket_url == "https://acme.atlassian.net/browse/REL-42"
    mock_search.assert_awaited_once()
    assert mock_search.call_args.args[2] == "REL-42"  # searched Slack using the ticket key


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
        patch.object(service.connector_service, "get_credential", new=AsyncMock(return_value=None)),
        patch.object(service, "engine_search", new=AsyncMock(return_value=[])),
    ):
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    assert result.timeline[0].jira_ticket_key == "REL-99"
    assert result.timeline[0].jira_ticket_url is None  # no Jira connected


async def test_trace_with_no_ticket_key_and_no_pr_skips_slack_search() -> None:
    ranges = [_blame_range("abc", message="tweak formatting")]

    with (
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="tok"),
        ),
        patch.object(service.code_context_service, "get_blame", new=AsyncMock(return_value=ranges)),
        patch.object(service.connector_service, "get_credential", new=AsyncMock(return_value=None)),
        patch.object(service, "engine_search", new=AsyncMock(return_value=[])) as mock_search,
    ):
        result = await service.trace(
            object(), _USER, owner="acme", repo="widgets", ref="main", path="x.py"
        )

    assert result.timeline[0].related_slack == []
    mock_search.assert_not_awaited()
