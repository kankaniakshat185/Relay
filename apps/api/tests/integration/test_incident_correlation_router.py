"""Router-level, same shape as `test_who_to_ask_router.py` /
`test_archaeology_router.py`: real DB for ingested items and the credential
lookup, GitHub's blame call mocked when the v2 file-trace path is exercised.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors.encryption import encrypt_token
from relay_api.connectors.models import ConnectorCredential
from relay_api.core.deps import get_current_user
from relay_api.engine.code_context.schemas import BlameRange
from relay_api.engine.ingestion import service as ingestion_service
from relay_api.engine.ingestion.schemas import NormalizedItem
from relay_api.main import app

_INCIDENT_AT = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def _item(external_id: str, title: str, occurred_at: datetime) -> NormalizedItem:
    return NormalizedItem(
        source="github",
        source_type="pull_request",
        external_id=external_id,
        title=title,
        body="body text",
        url="https://github.com/acme/widgets/pull/1",
        author="octocat",
        occurred_at=occurred_at,
    )


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


async def test_correlate_returns_only_items_inside_the_incident_window(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await ingestion_service.upsert_items(
        db,
        test_user.id,
        [
            _item("inside", "Inside the window", _INCIDENT_AT - timedelta(hours=1)),
            _item("outside", "Outside the window", _INCIDENT_AT - timedelta(days=30)),
        ],
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        response = await client.post(
            "/v1/incident-correlation",
            json={"incident_at": _INCIDENT_AT.isoformat(), "window_before_hours": 48},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["used_llm"] is False
    assert [s["title"] for s in body["sources"]] == ["Inside the window"]
    assert body["file_trace"] == []


async def test_correlate_with_file_path_but_missing_repo_fields_is_a_clean_422(
    client: AsyncClient, test_user: User
) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        response = await client.post(
            "/v1/incident-correlation",
            json={"incident_at": _INCIDENT_AT.isoformat(), "file_path": "src/x.py"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 422


async def test_correlate_with_file_path_traces_the_file_and_filters_to_the_window(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)
    in_window = BlameRange(
        starting_line=1,
        ending_line=5,
        commit_sha="in-window",
        commit_message="a fix",
        commit_url="https://github.com/acme/widgets/commit/in-window",
        committed_at=_INCIDENT_AT - timedelta(hours=1),
        author_name="Octocat",
        author_login="octocat",
        pull_request=None,
    )
    too_old = BlameRange(
        starting_line=1,
        ending_line=5,
        commit_sha="too-old",
        commit_message="unrelated",
        commit_url="https://github.com/acme/widgets/commit/too-old",
        committed_at=_INCIDENT_AT - timedelta(days=30),
        author_name="Octocat",
        author_login="octocat",
        pull_request=None,
    )

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch(
            "relay_api.engine.timeline.service.code_context_service.get_blame",
            new=AsyncMock(return_value=[in_window, too_old]),
        ):
            response = await client.post(
                "/v1/incident-correlation",
                json={
                    "incident_at": _INCIDENT_AT.isoformat(),
                    "owner": "acme",
                    "repo": "widgets",
                    "ref": "main",
                    "file_path": "src/x.py",
                },
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    trace = response.json()["file_trace"]
    assert [c["sha"] for c in trace] == ["in-window"]
