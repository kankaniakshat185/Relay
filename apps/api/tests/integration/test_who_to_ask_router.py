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
from relay_api.engine.code_context.schemas import BlameRange
from relay_api.main import app


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


def _blame_range(sha: str, author_login: str, committed_at: datetime) -> BlameRange:
    return BlameRange(
        starting_line=1,
        ending_line=5,
        commit_sha=sha,
        commit_message="msg",
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
