"""`connectors/github/ingest.py` orchestrates client calls into normalized
items — these tests mock `client` directly and check the `_REVIEW_FETCH_LIMIT`
cap (ADR 0016), the one piece of real logic in this module beyond
straight pass-through."""

from unittest.mock import AsyncMock, patch

from relay_api.connectors.github import ingest


def _repo(name: str = "widgets") -> dict:
    return {"owner": {"login": "acme"}, "name": name, "full_name": f"acme/{name}"}


def _pr(number: int) -> dict:
    return {
        "id": number * 100,
        "number": number,
        "title": f"PR {number}",
        "body": "",
        "html_url": f"https://github.com/acme/widgets/pull/{number}",
        "state": "open",
        "user": {"login": "octocat"},
        "updated_at": "2026-01-15T10:30:00Z",
    }


def _review(review_id: int) -> dict:
    return {
        "id": review_id,
        "user": {"login": "reviewer"},
        "body": "Looks good.",
        "state": "APPROVED",
        "html_url": f"https://github.com/acme/widgets/pull/1#pullrequestreview-{review_id}",
        "submitted_at": "2026-01-15T10:30:00Z",
    }


async def test_fetches_review_data_only_for_the_most_recently_updated_prs() -> None:
    # More PRs than `_REVIEW_FETCH_LIMIT` — `list_recent_pull_requests`
    # already returns them updated-desc, so this proves the cap takes the
    # *first* N, not an arbitrary subset.
    prs = [_pr(n) for n in range(1, ingest._REVIEW_FETCH_LIMIT + 5)]

    with (
        patch.object(ingest.client, "list_recent_repos", new=AsyncMock(return_value=[_repo()])),
        patch.object(ingest.client, "list_recent_pull_requests", new=AsyncMock(return_value=prs)),
        patch.object(
            ingest.client, "list_pr_reviews", new=AsyncMock(return_value=[])
        ) as mock_reviews,
        patch.object(
            ingest.client, "list_pr_review_comments", new=AsyncMock(return_value=[])
        ) as mock_comments,
        patch.object(ingest.client, "list_recent_commits", new=AsyncMock(return_value=[])),
    ):
        await ingest.fetch_normalized_items("token")

    assert mock_reviews.await_count == ingest._REVIEW_FETCH_LIMIT
    assert mock_comments.await_count == ingest._REVIEW_FETCH_LIMIT
    fetched_pr_numbers = {call.args[3] for call in mock_reviews.await_args_list}
    assert fetched_pr_numbers == set(range(1, ingest._REVIEW_FETCH_LIMIT + 1))


async def test_review_and_comment_items_carry_the_matching_pr_number() -> None:
    with (
        patch.object(ingest.client, "list_recent_repos", new=AsyncMock(return_value=[_repo()])),
        patch.object(
            ingest.client, "list_recent_pull_requests", new=AsyncMock(return_value=[_pr(1)])
        ),
        patch.object(ingest.client, "list_pr_reviews", new=AsyncMock(return_value=[_review(80)])),
        patch.object(
            ingest.client,
            "list_pr_review_comments",
            new=AsyncMock(
                return_value=[
                    {
                        "id": 1,
                        "path": "src/x.py",
                        "user": {"login": "reviewer"},
                        "body": "Nit.",
                        "html_url": "https://github.com/acme/widgets/pull/1#discussion_r1",
                        "created_at": "2026-01-15T09:00:00Z",
                    }
                ]
            ),
        ),
        patch.object(ingest.client, "list_recent_commits", new=AsyncMock(return_value=[])),
    ):
        items = await ingest.fetch_normalized_items("token")

    review_comment_items = [i for i in items if i.source_type == "review_comment"]
    assert len(review_comment_items) == 2
    assert all(i.extra["pr_number"] == 1 for i in review_comment_items)


async def test_empty_body_reviews_are_dropped_from_ingested_items() -> None:
    empty_review = {
        "id": 90,
        "user": {"login": "reviewer"},
        "body": "",
        "state": "APPROVED",
        "html_url": "https://github.com/acme/widgets/pull/1#pullrequestreview-90",
        "submitted_at": "2026-01-15T10:30:00Z",
    }

    with (
        patch.object(ingest.client, "list_recent_repos", new=AsyncMock(return_value=[_repo()])),
        patch.object(
            ingest.client, "list_recent_pull_requests", new=AsyncMock(return_value=[_pr(1)])
        ),
        patch.object(ingest.client, "list_pr_reviews", new=AsyncMock(return_value=[empty_review])),
        patch.object(ingest.client, "list_pr_review_comments", new=AsyncMock(return_value=[])),
        patch.object(ingest.client, "list_recent_commits", new=AsyncMock(return_value=[])),
    ):
        items = await ingest.fetch_normalized_items("token")

    assert not any(i.source_type == "review_comment" for i in items)
