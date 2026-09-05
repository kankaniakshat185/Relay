"""Router-level, same shape as `test_incident_correlation_router.py`:
real DB, `embed_texts` mocked so `find_related`'s query-embedding step
doesn't make a real API call."""

from datetime import UTC, datetime
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.core.deps import get_current_user
from relay_api.engine.indexing import service as indexing_service
from relay_api.engine.ingestion import service as ingestion_service
from relay_api.engine.ingestion.models import EMBEDDING_DIMENSIONS
from relay_api.engine.ingestion.schemas import NormalizedItem
from relay_api.main import app

_FAKE_VECTOR = [0.1] * EMBEDDING_DIMENSIONS


async def _fake_embed(texts: list[str]) -> list[list[float]]:
    return [_FAKE_VECTOR for _ in texts]


def _pr(number: int, ticket_key: str) -> NormalizedItem:
    return NormalizedItem(
        source="github",
        source_type="pull_request",
        external_id=f"pr-{number}",
        title=f"{ticket_key}: fix retry logic",
        body="",
        url=f"https://github.com/acme/widgets/pull/{number}",
        author="octocat",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={"repo": "acme/widgets", "state": "open", "number": number},
    )


def _slack_message(external_id: str, ticket_key: str) -> NormalizedItem:
    return NormalizedItem(
        source="slack",
        source_type="message",
        external_id=external_id,
        title=f"discussing {ticket_key}",
        body=f"a lot of back and forth about {ticket_key} here",
        url=f"https://acme.slack.com/archives/C1/{external_id}",
        author="alice",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_scan_flags_a_real_undocumented_pr(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    pr = _pr(1, "REL-42")
    messages = [_slack_message(f"msg-{i}", "REL-42") for i in range(2)]
    await ingestion_service.upsert_items(db, test_user.id, [pr, *messages])

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch.object(indexing_service, "embed_texts", new=_fake_embed):
            response = await client.post(
                "/v1/decision-debt/scan",
                json={"owner": "acme", "repo": "widgets", "min_discussion_items": 2},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["prs_scanned"] == 1
    assert [f["number"] for f in body["flagged"]] == [1]
    assert body["flagged"][0]["author_inactive"] is False


async def test_scan_with_no_ingested_prs_returns_an_empty_result(
    client: AsyncClient, test_user: User
) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        response = await client.post(
            "/v1/decision-debt/scan", json={"owner": "acme", "repo": "empty-repo"}
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body == {"flagged": [], "prs_scanned": 0, "decision_docs_found": 0}


async def test_scan_requires_login(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/decision-debt/scan", json={"owner": "acme", "repo": "widgets"}
    )

    assert response.status_code == 401
