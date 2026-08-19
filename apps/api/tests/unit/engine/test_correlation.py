"""`engine/correlation` — extraction/URL-building are pure and tested
directly; `find_related`/`find_similar_jira_issues` mock
`engine.indexing.service.search`, the same boundary
`features/archaeology`'s tests used to mock before this logic moved here."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from relay_api.engine.correlation import service
from relay_api.engine.ingestion.models import IngestedItem


def test_extract_ticket_key_finds_a_key_in_the_first_matching_text() -> None:
    key = service.extract_ticket_key("no key here", "REL-42: fix retry logic", "unused")

    assert key == "REL-42"


def test_extract_ticket_key_returns_none_when_nothing_matches() -> None:
    key = service.extract_ticket_key("just a normal message", "", "")

    assert key is None


def test_extract_ticket_key_checks_texts_in_order() -> None:
    # Both contain a key — the first text's key wins.
    key = service.extract_ticket_key("REL-1 in commit message", "REL-2 in pr title")

    assert key == "REL-1"


def test_build_jira_ticket_url_with_a_connected_site() -> None:
    url = service.build_jira_ticket_url("https://acme.atlassian.net", "REL-42")

    assert url == "https://acme.atlassian.net/browse/REL-42"


def test_build_jira_ticket_url_strips_trailing_slash_handled_by_caller() -> None:
    # get_jira_site_url is what strips the trailing slash (tested via the
    # DB-backed path below) — build_jira_ticket_url just concatenates.
    url = service.build_jira_ticket_url("https://acme.atlassian.net", "REL-1")

    assert "//browse" not in url


def test_build_jira_ticket_url_with_no_connected_site_returns_none() -> None:
    url = service.build_jira_ticket_url(None, "REL-42")

    assert url is None


async def test_get_jira_site_url_returns_none_when_not_connected() -> None:
    with patch.object(
        service.connector_service, "get_credential", new=AsyncMock(return_value=None)
    ):
        site_url = await service.get_jira_site_url(object(), uuid.uuid4())

    assert site_url is None


async def test_get_jira_site_url_strips_trailing_slash() -> None:
    credential = type("C", (), {"external_account_label": "https://acme.atlassian.net/"})()
    with patch.object(
        service.connector_service, "get_credential", new=AsyncMock(return_value=credential)
    ):
        site_url = await service.get_jira_site_url(object(), uuid.uuid4())

    assert site_url == "https://acme.atlassian.net"


async def test_find_related_returns_empty_list_for_no_query() -> None:
    with patch.object(service, "engine_search", new=AsyncMock(return_value=[])) as mock_search:
        result = await service.find_related(object(), uuid.uuid4(), None, sources=["slack"])

    assert result == []
    mock_search.assert_not_awaited()


async def test_find_related_shapes_and_truncates_excerpt() -> None:
    long_body = "word " * 100  # well over the 200-char excerpt limit
    item = IngestedItem(
        source="slack",
        source_type="message",
        external_id="msg-1",
        title="Discussion",
        body=long_body,
        url="https://acme.slack.com/archives/C1/p1",
        author="alice",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    with patch.object(service, "engine_search", new=AsyncMock(return_value=[item])):
        result = await service.find_related(object(), uuid.uuid4(), "REL-42", sources=["slack"])

    assert len(result) == 1
    assert result[0].source == "slack"
    assert result[0].url == "https://acme.slack.com/archives/C1/p1"
    assert len(result[0].excerpt) <= 200


async def test_find_related_passes_query_sources_and_limit_through() -> None:
    with patch.object(service, "engine_search", new=AsyncMock(return_value=[])) as mock_search:
        await service.find_related(object(), uuid.uuid4(), "REL-42", sources=["jira"], limit=5)

    mock_search.assert_awaited_once()
    args = mock_search.call_args
    assert args.args[2] == "REL-42"
    assert args.kwargs["sources"] == ["jira"]
    assert args.kwargs["limit"] == 5


async def test_find_related_asserts_a_minimum_relevance_score() -> None:
    # Regression test: without this, "related" results always show the
    # top N by score even when nothing actually matches — see
    # `_MIN_RELEVANCE_SCORE`'s docstring for the real data behind 0.4.
    with patch.object(service, "engine_search", new=AsyncMock(return_value=[])) as mock_search:
        await service.find_related(object(), uuid.uuid4(), "REL-42", sources=["slack"])

    assert mock_search.call_args.kwargs["min_score"] == service._MIN_RELEVANCE_SCORE


def _jira_item(external_id: str, key: str, title: str, body: str) -> IngestedItem:
    return IngestedItem(
        source="jira",
        source_type="issue",
        external_id=external_id,
        title=title,
        body=body,
        url=f"https://acme.atlassian.net/browse/{key}",
        author="alice",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={"key": key},
    )


async def test_find_similar_jira_issues_returns_empty_when_ticket_not_ingested() -> None:
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)

    result = await service.find_similar_jira_issues(db, uuid.uuid4(), "REL-42")

    assert result == []


async def test_find_similar_jira_issues_queries_using_the_tickets_own_content() -> None:
    ticket = _jira_item("1", "REL-42", "Payment timeout", "Timeouts happen under load")
    db = MagicMock()
    db.scalar = AsyncMock(return_value=ticket)

    with patch.object(service, "find_related", new=AsyncMock(return_value=[])) as mock_find_related:
        await service.find_similar_jira_issues(db, uuid.uuid4(), "REL-42")

    mock_find_related.assert_awaited_once()
    args = mock_find_related.call_args
    assert "Payment timeout" in args.args[2]
    assert "Timeouts happen under load" in args.args[2]
    assert args.kwargs["sources"] == ["jira"]


async def test_find_similar_jira_issues_excludes_the_ticket_itself() -> None:
    ticket = _jira_item("1", "REL-42", "Payment timeout", "body")
    other = service.RelatedItem(
        source="jira",
        title="Other issue",
        url="https://acme.atlassian.net/browse/REL-99",
        excerpt="unrelated",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    self_match = service.RelatedItem(
        source="jira",
        title="Payment timeout",
        url=ticket.url,
        excerpt="body",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    db = MagicMock()
    db.scalar = AsyncMock(return_value=ticket)

    with patch.object(service, "find_related", new=AsyncMock(return_value=[self_match, other])):
        result = await service.find_similar_jira_issues(db, uuid.uuid4(), "REL-42")

    assert result == [other]


def _review_item(state: str | None, occurred_at: datetime) -> service.ReviewItem:
    return service.ReviewItem(
        author="reviewer",
        excerpt="x",
        url="https://github.com/x",
        occurred_at=occurred_at,
        state=state,
    )


async def test_find_review_comments_for_pr_shapes_items_oldest_first() -> None:
    item = IngestedItem(
        source="github",
        source_type="review_comment",
        external_id="review-1",
        title="Review: APPROVED",
        body="Looks good, nice work handling the edge case.",
        url="https://github.com/acme/widgets/pull/7#pullrequestreview-1",
        author="reviewer",
        occurred_at=datetime(2026, 1, 15, tzinfo=UTC),
        extra={"repo": "acme/widgets", "pr_number": 7, "kind": "review", "state": "APPROVED"},
    )
    scalars_result = MagicMock()
    scalars_result.all.return_value = [item]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_result
    db = MagicMock()
    db.execute = AsyncMock(return_value=execute_result)

    result = await service.find_review_comments_for_pr(db, uuid.uuid4(), "acme", "widgets", 7)

    assert len(result) == 1
    assert result[0].author == "reviewer"
    assert result[0].state == "APPROVED"
    assert result[0].url == item.url


def test_has_unresolved_concerns_true_when_the_latest_verdict_is_changes_requested() -> None:
    reviews = [
        _review_item("APPROVED", datetime(2026, 1, 1, tzinfo=UTC)),
        _review_item("CHANGES_REQUESTED", datetime(2026, 1, 2, tzinfo=UTC)),
    ]

    assert service.has_unresolved_concerns(reviews) is True


def test_has_unresolved_concerns_false_when_approved_comes_after_changes_requested() -> None:
    reviews = [
        _review_item("CHANGES_REQUESTED", datetime(2026, 1, 1, tzinfo=UTC)),
        _review_item("APPROVED", datetime(2026, 1, 2, tzinfo=UTC)),
    ]

    assert service.has_unresolved_concerns(reviews) is False


def test_has_unresolved_concerns_false_with_no_verdicts_at_all() -> None:
    # Only an inline comment (state is None) — nothing counts as a verdict.
    reviews = [_review_item(None, datetime(2026, 1, 1, tzinfo=UTC))]

    assert service.has_unresolved_concerns(reviews) is False


def test_has_unresolved_concerns_ignores_inline_comments_when_finding_the_latest_verdict() -> None:
    reviews = [
        _review_item("CHANGES_REQUESTED", datetime(2026, 1, 1, tzinfo=UTC)),
        _review_item(None, datetime(2026, 1, 5, tzinfo=UTC)),  # later, but not a verdict
    ]

    assert service.has_unresolved_concerns(reviews) is True
