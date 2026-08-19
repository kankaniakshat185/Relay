"""Router-level: real DB (credentials, Slack correlation search), GitHub's
live blame call mocked at `engine.code_context.service.get_blame` — the
one call that would otherwise need a real GitHub account. Establishes the
dependency-override pattern (`get_current_user`) for testing an
authenticated route end to end, not just its service function.
"""

from datetime import UTC, datetime
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


async def test_trace_requires_github_to_be_connected(client: AsyncClient, test_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        response = await client.post(
            "/v1/archaeology/trace",
            json={"owner": "acme", "repo": "widgets", "ref": "main", "path": "src/x.py"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400
    assert "github" in response.json()["detail"].lower()


async def test_trace_correlates_a_real_slack_message_by_ticket_key(
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

    blame_ranges = [
        BlameRange(
            starting_line=1,
            ending_line=5,
            commit_sha="abc123",
            commit_message="REL-42: add retry logic",
            commit_url="https://github.com/acme/widgets/commit/abc123",
            committed_at=datetime(2026, 1, 1, tzinfo=UTC),
            author_name="Octocat",
            author_login="octocat",
            pull_request=AssociatedPullRequest(
                number=1,
                title="REL-42 retry logic",
                url="https://github.com/acme/widgets/pull/1",
                body="",
            ),
        )
    ]

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with (
            patch(
                "relay_api.features.archaeology.service.code_context_service.get_blame",
                new=AsyncMock(return_value=blame_ranges),
            ),
            # The trace endpoint's Slack correlation runs a real hybrid
            # search, which embeds the query — mocked here for the same
            # reason it's mocked around indexing above, not a live OpenAI
            # call either way.
            patch.object(
                indexing_service, "embed_texts", new=AsyncMock(return_value=[_FAKE_VECTOR])
            ),
        ):
            response = await client.post(
                "/v1/archaeology/trace",
                json={"owner": "acme", "repo": "widgets", "ref": "main", "path": "src/x.py"},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    timeline = response.json()["timeline"]
    assert len(timeline) == 1
    assert timeline[0]["jira_ticket_key"] == "REL-42"
    assert any(
        msg["url"] == "https://acme.slack.com/archives/C1/p1"
        for msg in timeline[0]["related_slack"]
    )


async def test_trace_finds_similar_past_jira_issues(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)

    # The ticket the commit references, plus a semantically similar past
    # issue — both real, ingested, indexed Jira issues, not mocked.
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

    blame_ranges = [
        BlameRange(
            starting_line=1,
            ending_line=5,
            commit_sha="abc123",
            commit_message="REL-42: add retry logic",
            commit_url="https://github.com/acme/widgets/commit/abc123",
            committed_at=datetime(2026, 1, 1, tzinfo=UTC),
            author_name="Octocat",
            author_login="octocat",
            pull_request=None,
        )
    ]

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with (
            patch(
                "relay_api.features.archaeology.service.code_context_service.get_blame",
                new=AsyncMock(return_value=blame_ranges),
            ),
            patch.object(indexing_service, "embed_texts", new=_fake_embed_texts),
        ):
            response = await client.post(
                "/v1/archaeology/trace",
                json={"owner": "acme", "repo": "widgets", "ref": "main", "path": "src/x.py"},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    timeline = response.json()["timeline"]
    similar = timeline[0]["similar_issues"]
    assert any(issue["url"] == "https://acme.atlassian.net/browse/REL-7" for issue in similar)
    # The current ticket never shows up as "similar" to itself.
    assert not any(issue["url"] == "https://acme.atlassian.net/browse/REL-42" for issue in similar)


async def test_trace_directory_mode_end_to_end(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)

    directory_blame = DirectoryBlame(
        files=[
            FileBlame(
                path="src/payments/handler.py",
                ranges=[
                    BlameRange(
                        starting_line=1,
                        ending_line=5,
                        commit_sha="abc123",
                        commit_message="Fix retry logic",
                        commit_url="https://github.com/acme/widgets/commit/abc123",
                        committed_at=datetime(2026, 1, 1, tzinfo=UTC),
                        author_name="Octocat",
                        author_login="octocat",
                    )
                ],
            ),
            FileBlame(
                path="src/payments/refunds.py",
                ranges=[
                    BlameRange(
                        starting_line=1,
                        ending_line=5,
                        commit_sha="abc123",  # same commit, different file
                        commit_message="Fix retry logic",
                        commit_url="https://github.com/acme/widgets/commit/abc123",
                        committed_at=datetime(2026, 1, 1, tzinfo=UTC),
                        author_name="Octocat",
                        author_login="octocat",
                    )
                ],
            ),
        ],
        files_total=2,
        files_analyzed=2,
        files_skipped=0,
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch(
            "relay_api.features.archaeology.service.code_context_service.get_blame_for_directory",
            new=AsyncMock(return_value=directory_blame),
        ):
            response = await client.post(
                "/v1/archaeology/trace",
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
    assert body["files_analyzed"] == 2
    assert len(body["timeline"]) == 1  # same commit in both files collapses to one entry
    assert sorted(body["timeline"][0]["files_touched"]) == [
        "src/payments/handler.py",
        "src/payments/refunds.py",
    ]


async def test_search_resolves_a_real_ingested_commit_to_its_changed_files(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    """The ticket/PR-first entry point (ADR 0015): a real ingested commit
    is found by a real DB text search, then its changed files are
    resolved via a live GitHub call — mocked here, the one call that
    would otherwise need a real GitHub account."""
    await _connect_github(db, test_user)

    commit_item = NormalizedItem(
        source="github",
        source_type="commit",
        external_id="abc123fullsha",
        title="REL-42: add retry logic",
        body="REL-42: add retry logic",
        url="https://github.com/acme/widgets/commit/abc123fullsha",
        author="octocat",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={"repo": "acme/widgets", "sha": "abc123f"},
    )
    await ingestion_service.upsert_items(db, test_user.id, [commit_item])
    to_index = await ingestion_service.get_items_needing_indexing(db, test_user.id)
    with patch.object(indexing_service, "embed_texts", new=_fake_embed_texts):
        await indexing_service.index_items(db, to_index)

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with (
            patch.object(indexing_service, "embed_texts", new=_fake_embed_texts),
            patch(
                "relay_api.engine.code_search.service.list_commit_files",
                new=AsyncMock(return_value=["src/retry.py"]),
            ),
        ):
            response = await client.get("/v1/archaeology/search", params={"q": "REL-42"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    matches = response.json()
    assert len(matches) == 1
    assert matches[0]["kind"] == "commit"
    assert matches[0]["sha"] == "abc123fullsha"
    assert matches[0]["files"] == ["src/retry.py"]


async def test_trace_surfaces_real_review_comments_and_the_unresolved_flag(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    """ADR 0016: a commit's PR review commentary is a real ingested item
    resolved via a direct DB filter, not a mock — only the live blame
    call is mocked."""
    await _connect_github(db, test_user)

    changes_requested = NormalizedItem(
        source="github",
        source_type="review_comment",
        external_id="review-1",
        title="Review: CHANGES_REQUESTED",
        body="Please add a test for the timeout path.",
        url="https://github.com/acme/widgets/pull/7#pullrequestreview-1",
        author="dave",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={
            "repo": "acme/widgets",
            "pr_number": 7,
            "kind": "review",
            "state": "CHANGES_REQUESTED",
        },
    )
    await ingestion_service.upsert_items(db, test_user.id, [changes_requested])

    blame_ranges = [
        BlameRange(
            starting_line=1,
            ending_line=5,
            commit_sha="abc123",
            commit_message="REL-42: add retry logic",
            commit_url="https://github.com/acme/widgets/commit/abc123",
            committed_at=datetime(2026, 1, 1, tzinfo=UTC),
            author_name="Octocat",
            author_login="octocat",
            pull_request=AssociatedPullRequest(
                number=7,
                title="REL-42 retry logic",
                url="https://github.com/acme/widgets/pull/7",
                body="",
            ),
        )
    ]

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with (
            patch(
                "relay_api.features.archaeology.service.code_context_service.get_blame",
                new=AsyncMock(return_value=blame_ranges),
            ),
            patch.object(
                indexing_service, "embed_texts", new=AsyncMock(return_value=[_FAKE_VECTOR])
            ),
        ):
            response = await client.post(
                "/v1/archaeology/trace",
                json={"owner": "acme", "repo": "widgets", "ref": "main", "path": "src/x.py"},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    entry = response.json()["timeline"][0]
    assert len(entry["review_comments"]) == 1
    assert entry["review_comments"][0]["author"] == "dave"
    assert entry["pull_request"]["has_unresolved_review"] is True
