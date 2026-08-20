"""HTTP round-trip for `/v1/notes` — the embedding call is mocked (same
reasoning as `test_notes_service.py`); everything else is real."""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.core.deps import get_current_user
from relay_api.engine.indexing import service as indexing_service
from relay_api.engine.ingestion.models import EMBEDDING_DIMENSIONS
from relay_api.main import app

_FAKE_VECTOR = [0.1] * EMBEDDING_DIMENSIONS


def _embed_mock() -> AsyncMock:
    return AsyncMock(return_value=[_FAKE_VECTOR])


async def test_create_list_update_delete_round_trip(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
            create_response = await client.post(
                "/v1/notes",
                json={"title": "First note", "body": "Some content", "tags": ["backend"]},
            )
            assert create_response.status_code == 201
            note_id = create_response.json()["id"]

            list_response = await client.get("/v1/notes")
            assert list_response.status_code == 200
            assert [n["title"] for n in list_response.json()] == ["First note"]

            update_response = await client.patch(
                f"/v1/notes/{note_id}", json={"title": "Renamed note"}
            )
            assert update_response.status_code == 200
            assert update_response.json()["title"] == "Renamed note"

            delete_response = await client.delete(f"/v1/notes/{note_id}")
            assert delete_response.status_code == 204

        empty_list = await client.get("/v1/notes")
        assert empty_list.json() == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def test_delete_all_notes(client: AsyncClient, test_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
            await client.post("/v1/notes", json={"title": "One", "body": ""})
            await client.post("/v1/notes", json={"title": "Two", "body": ""})

        delete_all_response = await client.delete("/v1/notes")
        list_response = await client.get("/v1/notes")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert delete_all_response.status_code == 200
    assert delete_all_response.json() == {"deleted_count": 2}
    assert list_response.json() == []


async def test_update_and_delete_a_missing_note_are_404(
    client: AsyncClient, test_user: User
) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        missing_id = "00000000-0000-0000-0000-000000000000"
        update_response = await client.patch(f"/v1/notes/{missing_id}", json={"title": "x"})
        delete_response = await client.delete(f"/v1/notes/{missing_id}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert update_response.status_code == 404
    assert delete_response.status_code == 404


async def test_export_returns_a_markdown_document(client: AsyncClient, test_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
            await client.post("/v1/notes", json={"title": "Exportable", "body": "content here"})
        export_response = await client.get("/v1/notes/export")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/markdown")
    assert "## Exportable" in export_response.text
    assert "content here" in export_response.text


async def test_create_a_note_linked_to_an_existing_item(
    client: AsyncClient, test_user: User
) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
            response = await client.post(
                "/v1/notes",
                json={
                    "title": "Annotation",
                    "body": "why this PR does X",
                    "links": [
                        {
                            "source": "github",
                            "url": "https://github.com/acme/widgets/pull/7",
                            "title": "Fix retry logic",
                        }
                    ],
                },
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    body = response.json()
    assert body["links"] == [
        {
            "source": "github",
            "url": "https://github.com/acme/widgets/pull/7",
            "title": "Fix retry logic",
        }
    ]


async def test_attach_a_link_to_an_existing_note(client: AsyncClient, test_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
            create_response = await client.post(
                "/v1/notes", json={"title": "Freeform note", "body": ""}
            )
            note_id = create_response.json()["id"]

            link_response = await client.post(
                f"/v1/notes/{note_id}/links",
                json={
                    "source": "jira",
                    "url": "https://acme.atlassian.net/browse/REL-42",
                    "title": "REL-42",
                },
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert link_response.status_code == 200
    assert link_response.json()["links"] == [
        {"source": "jira", "url": "https://acme.atlassian.net/browse/REL-42", "title": "REL-42"}
    ]


async def test_attach_a_link_to_a_missing_note_is_404(client: AsyncClient, test_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        missing_id = "00000000-0000-0000-0000-000000000000"
        response = await client.post(
            f"/v1/notes/{missing_id}/links",
            json={"source": "github", "url": "https://github.com/acme/widgets", "title": "x"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404


async def test_remove_a_link_by_index(client: AsyncClient, test_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        with patch.object(indexing_service, "embed_texts", new=_embed_mock()):
            create_response = await client.post(
                "/v1/notes",
                json={
                    "title": "Two links",
                    "body": "",
                    "links": [
                        {
                            "source": "github",
                            "url": "https://github.com/acme/widgets/pull/1",
                            "title": "PR",
                        },
                        {
                            "source": "jira",
                            "url": "https://acme.atlassian.net/browse/REL-1",
                            "title": "REL-1",
                        },
                    ],
                },
            )
            note_id = create_response.json()["id"]

            remove_response = await client.delete(f"/v1/notes/{note_id}/links/0")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert remove_response.status_code == 200
    assert remove_response.json()["links"] == [
        {"source": "jira", "url": "https://acme.atlassian.net/browse/REL-1", "title": "REL-1"}
    ]


async def test_remove_a_link_with_an_out_of_range_index_is_404(
    client: AsyncClient, test_user: User
) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        create_response = await client.post("/v1/notes", json={"title": "No links", "body": ""})
        note_id = create_response.json()["id"]
        response = await client.delete(f"/v1/notes/{note_id}/links/0")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404
