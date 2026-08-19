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
from relay_api.engine.code_context.schemas import AssociatedPullRequest, BlameRange
from relay_api.engine.indexing import service as indexing_service
from relay_api.engine.ingestion import service as ingestion_service
from relay_api.engine.ingestion.models import EMBEDDING_DIMENSIONS
from relay_api.engine.ingestion.schemas import NormalizedItem
from relay_api.main import app

_FAKE_VECTOR = [0.1] * EMBEDDING_DIMENSIONS


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
