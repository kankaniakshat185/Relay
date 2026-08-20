"""Router-level, same shape as `test_archaeology_router.py`: real DB for
the credential lookup, GitHub's blame call mocked."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors.encryption import encrypt_token
from relay_api.connectors.models import ConnectorCredential
from relay_api.core.deps import get_current_user
from relay_api.engine.code_context.schemas import (
    AssociatedPullRequest,
    BlameRange,
    DirectoryBlame,
    FileBlame,
)
from relay_api.engine.indexing import service as indexing_service
from relay_api.engine.ingestion import service as ingestion_service
from relay_api.engine.ingestion.models import EMBEDDING_DIMENSIONS
from relay_api.engine.ingestion.schemas import NormalizedItem
from relay_api.main import app

_FAKE_VECTOR = [0.1] * EMBEDDING_DIMENSIONS


async def _fake_embed_texts(texts: list[str]) -> list[list[float]]:
    """A real `embed_texts` returns one vector per input text — the fixed
    single-vector mock other tests use only works for single-item
    batches; this scales with whatever's actually passed in."""
    return [_FAKE_VECTOR for _ in texts]


async def _connect_github(db: AsyncSession, user: User) -> None:
    db.add(
        ConnectorCredential(
            user_id=user.id,
            provider="github",
            access_token_encrypted=encrypt_token("gh-token"),
            scope="repo",
            external_account_id="1",
            external_account_label="octocat",
        )
    )
    await db.commit()


def _blame_range(
    sha: str, author_login: str, committed_at: datetime, message: str = "msg"
) -> BlameRange:
    return BlameRange(
        starting_line=1,
        ending_line=5,
        commit_sha=sha,
        commit_message=message,
        commit_url=f"https://github.com/acme/widgets/commit/{sha}",
        committed_at=committed_at,
        author_name=author_login,
        author_login=author_login,
        pull_request=None,
    )


async def test_rank_requires_github_to_be_connected(client: AsyncClient, test_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        response = await client.post(
            "/v1/who-to-ask/rank",
            json={"owner": "acme", "repo": "widgets", "ref": "main", "path": "src/x.py"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400
    assert "github" in response.json()["detail"].lower()


async def test_rank_returns_ranked_people_for_a_real_connected_user(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    ranges = [
        _blame_range("recent", "carol", now - timedelta(days=1)),
        _blame_range("old-1", "dave", now - timedelta(days=240)),
        _blame_range("old-2", "dave", now - timedelta(days=241)),
    ]

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch(
            "relay_api.features.who_to_ask.service.code_context_service.get_blame",
            new=AsyncMock(return_value=ranges),
        ):
            recency_response = await client.post(
                "/v1/who-to-ask/rank",
                json={
                    "owner": "acme",
                    "repo": "widgets",
                    "ref": "main",
                    "path": "src/x.py",
                    "strategy": "recency",
                },
            )
            frequency_response = await client.post(
                "/v1/who-to-ask/rank",
                json={
                    "owner": "acme",
                    "repo": "widgets",
                    "ref": "main",
                    "path": "src/x.py",
                    "strategy": "frequency",
                },
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert recency_response.status_code == 200
    assert recency_response.json()["people"][0]["author"] == "carol"
    assert frequency_response.status_code == 200
    assert frequency_response.json()["people"][0]["author"] == "dave"


async def test_rank_directory_mode_dedupes_a_commit_across_files(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    # Same commit, same author, touching two different files in the
    # directory — must count as one touch, not two.
    directory_blame = DirectoryBlame(
        files=[
            FileBlame(path="src/payments/handler.py", ranges=[_blame_range("abc", "carol", now)]),
            FileBlame(path="src/payments/refunds.py", ranges=[_blame_range("abc", "carol", now)]),
        ],
        files_total=2,
        files_analyzed=2,
        files_skipped=0,
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch(
            "relay_api.features.who_to_ask.service.code_context_service.get_blame_for_directory",
            new=AsyncMock(return_value=directory_blame),
        ):
            response = await client.post(
                "/v1/who-to-ask/rank",
                json={
                    "owner": "acme",
                    "repo": "widgets",
                    "ref": "main",
                    "path": "src/payments",
                    "target_type": "directory",
                },
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["files_total"] == 2
    assert len(body["people"]) == 1
    assert body["people"][0]["touch_count"] == 1


async def test_rank_correlates_a_real_slack_message_by_ticket_key(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)

    slack_item = NormalizedItem(
        source="slack",
        source_type="message",
        external_id="msg-1",
        title="REL-42 discussion",
        body="We decided to add retry logic for REL-42 after the outage.",
        url="https://acme.slack.com/archives/C1/p1",
        author="alice",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await ingestion_service.upsert_items(db, test_user.id, [slack_item])
    to_index = await ingestion_service.get_items_needing_indexing(db, test_user.id)
    with patch.object(indexing_service, "embed_texts", new=AsyncMock(return_value=[_FAKE_VECTOR])):
        await indexing_service.index_items(db, to_index)

    ranges = [
        _blame_range("abc", "carol", datetime(2026, 1, 1, tzinfo=UTC), "REL-42: add retry logic")
    ]

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with (
            patch(
                "relay_api.features.who_to_ask.service.code_context_service.get_blame",
                new=AsyncMock(return_value=ranges),
            ),
            patch.object(
                indexing_service, "embed_texts", new=AsyncMock(return_value=[_FAKE_VECTOR])
            ),
        ):
            response = await client.post(
                "/v1/who-to-ask/rank",
                json={"owner": "acme", "repo": "widgets", "ref": "main", "path": "src/x.py"},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    person = response.json()["people"][0]
    assert person["jira_ticket_key"] == "REL-42"
    assert any(
        msg["url"] == "https://acme.slack.com/archives/C1/p1" for msg in person["related_slack"]
    )


async def test_rank_finds_similar_past_jira_issues(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)

    current_ticket = NormalizedItem(
        source="jira",
        source_type="issue",
        external_id="1",
        title="Payment retries time out under load",
        body="Payment retry requests are timing out when traffic spikes.",
        url="https://acme.atlassian.net/browse/REL-42",
        author="alice",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={"key": "REL-42"},
    )
    past_ticket = NormalizedItem(
        source="jira",
        source_type="issue",
        external_id="2",
        title="Checkout retries time out under load",
        body="Checkout retry requests are timing out during traffic spikes.",
        url="https://acme.atlassian.net/browse/REL-7",
        author="bob",
        occurred_at=datetime(2025, 6, 1, tzinfo=UTC),
        extra={"key": "REL-7"},
    )
    await ingestion_service.upsert_items(db, test_user.id, [current_ticket, past_ticket])
    to_index = await ingestion_service.get_items_needing_indexing(db, test_user.id)
    with patch.object(indexing_service, "embed_texts", new=_fake_embed_texts):
        await indexing_service.index_items(db, to_index)

    ranges = [
        _blame_range("abc", "carol", datetime(2026, 1, 1, tzinfo=UTC), "REL-42: add retry logic")
    ]

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with (
            patch(
                "relay_api.features.who_to_ask.service.code_context_service.get_blame",
                new=AsyncMock(return_value=ranges),
            ),
            patch.object(indexing_service, "embed_texts", new=_fake_embed_texts),
        ):
            response = await client.post(
                "/v1/who-to-ask/rank",
                json={"owner": "acme", "repo": "widgets", "ref": "main", "path": "src/x.py"},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    person = response.json()["people"][0]
    similar = person["similar_issues"]
    assert any(issue["url"] == "https://acme.atlassian.net/browse/REL-7" for issue in similar)
    assert not any(issue["url"] == "https://acme.atlassian.net/browse/REL-42" for issue in similar)


async def test_search_resolves_a_real_ingested_pull_request_to_its_changed_files(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    """Same `/search` entry point as Archaeology's (ADR 0015) — this is
    the second router it's mounted on, so this test only needs to prove
    the route wires through correctly, not re-prove
    `find_files_for_query`'s own behavior (already covered by the unit
    tests and Archaeology's integration test)."""
    await _connect_github(db, test_user)

    pr_item = NormalizedItem(
        source="github",
        source_type="pull_request",
        external_id="99999",
        title="REL-42: add retry logic",
        body="REL-42: add retry logic",
        url="https://github.com/acme/widgets/pull/7",
        author="octocat",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={"repo": "acme/widgets", "state": "open", "number": 7},
    )
    await ingestion_service.upsert_items(db, test_user.id, [pr_item])
    to_index = await ingestion_service.get_items_needing_indexing(db, test_user.id)
    with patch.object(indexing_service, "embed_texts", new=_fake_embed_texts):
        await indexing_service.index_items(db, to_index)

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with (
            patch.object(indexing_service, "embed_texts", new=_fake_embed_texts),
            patch(
                "relay_api.engine.code_search.service.list_pr_files",
                new=AsyncMock(return_value=["src/retry.py"]),
            ),
        ):
            response = await client.get("/v1/who-to-ask/search", params={"q": "REL-42"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    matches = response.json()
    assert len(matches) == 1
    assert matches[0]["kind"] == "pull_request"
    assert matches[0]["pr_number"] == 7
    assert matches[0]["files"] == ["src/retry.py"]


async def test_rank_pull_request_mode_dedupes_a_commit_across_the_prs_changed_files(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    """PR Blast Radius — same dedup guarantee as directory mode
    (`test_rank_directory_mode_dedupes_a_commit_across_files` above), fed
    by `get_blame_for_pull_request` instead of `get_blame_for_directory`."""
    await _connect_github(db, test_user)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    pr_blame = DirectoryBlame(
        files=[
            FileBlame(path="src/payments/handler.py", ranges=[_blame_range("abc", "carol", now)]),
            FileBlame(path="src/payments/refunds.py", ranges=[_blame_range("abc", "carol", now)]),
        ],
        files_total=2,
        files_analyzed=2,
        files_skipped=0,
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch(
            "relay_api.features.who_to_ask.service.code_context_service.get_blame_for_pull_request",
            new=AsyncMock(return_value=pr_blame),
        ) as mock_get_blame:
            response = await client.post(
                "/v1/who-to-ask/rank",
                json={
                    "owner": "acme",
                    "repo": "widgets",
                    "ref": "main",
                    "path": "",
                    "target_type": "pull_request",
                    "pr_number": 7,
                },
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["files_total"] == 2
    assert len(body["people"]) == 1
    assert body["people"][0]["touch_count"] == 1
    mock_get_blame.assert_awaited_once_with("gh-token", "acme", "widgets", "main", 7)


async def test_rank_pull_request_mode_without_a_pr_number_is_a_clean_422(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        response = await client.post(
            "/v1/who-to-ask/rank",
            json={
                "owner": "acme",
                "repo": "widgets",
                "ref": "main",
                "path": "",
                "target_type": "pull_request",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 422


async def test_rank_surfaces_a_review_only_contributor(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    """ADR 0016: someone who reviewed a PR but never committed to it
    still shows up in rankings, with `commits == []` and their review in
    `reviews` — the real functional gap this build closes. Uses a real
    ingested review item and a real DB filter
    (`find_review_comments_for_pr`), not a mock — only the live blame call
    is mocked."""
    await _connect_github(db, test_user)

    review_item = NormalizedItem(
        source="github",
        source_type="review_comment",
        external_id="review-1",
        title="Review: APPROVED",
        body="Looks good, nice work on the retry logic.",
        url="https://github.com/acme/widgets/pull/7#pullrequestreview-1",
        author="dave",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={"repo": "acme/widgets", "pr_number": 7, "kind": "review", "state": "APPROVED"},
    )
    # No indexing step — `find_review_comments_for_pr` is a direct
    # `extra->>'pr_number'` filter, not a search, so it doesn't need an
    # embedding.
    await ingestion_service.upsert_items(db, test_user.id, [review_item])

    ranges = [
        BlameRange(
            starting_line=1,
            ending_line=5,
            commit_sha="abc",
            commit_message="REL-42: fix retry logic",
            commit_url="https://github.com/acme/widgets/commit/abc",
            committed_at=datetime(2026, 1, 1, tzinfo=UTC),
            author_name="carol",
            author_login="carol",
            pull_request=AssociatedPullRequest(
                number=7,
                title="REL-42 fix retry logic",
                url="https://github.com/acme/widgets/pull/7",
                body="",
            ),
        )
    ]

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch(
            "relay_api.features.who_to_ask.service.code_context_service.get_blame",
            new=AsyncMock(return_value=ranges),
        ):
            response = await client.post(
                "/v1/who-to-ask/rank",
                json={"owner": "acme", "repo": "widgets", "ref": "main", "path": "src/x.py"},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    people_by_author = {p["author"]: p for p in response.json()["people"]}
    assert "dave" in people_by_author
    dave = people_by_author["dave"]
    assert dave["commits"] == []
    assert len(dave["reviews"]) == 1
    assert dave["reviews"][0]["pr_number"] == 7

    carol = people_by_author["carol"]
    assert len(carol["commits"]) == 1
    assert carol["reviews"] == []
