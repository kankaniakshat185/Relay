"""`get_blame`'s response shaping and error mapping — GraphQL's quirk of
returning 200 with a top-level `errors` array (rather than an HTTP error
status) for a bad query is the main thing worth testing here."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from relay_api.connectors.github import graphql_client


def _mock_client(response: httpx.Response) -> MagicMock:
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=response)
    return client


def _graphql_response(body: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", graphql_client._GRAPHQL_URL)
    return httpx.Response(status_code, json=body, request=request)


def _blame_payload(ranges: list[dict]) -> dict:
    return {
        "data": {
            "repository": {"object": {"blame": {"ranges": ranges}}},
        }
    }


_COMMIT = {
    "oid": "abc123",
    "message": "Fix retry logic",
    "committedDate": "2026-01-01T00:00:00Z",
    "url": "https://github.com/acme/widgets/commit/abc123",
    "author": {"name": "Octocat", "user": {"login": "octocat"}},
    "associatedPullRequests": {
        "nodes": [
            {
                "number": 42,
                "title": "Fix retry logic",
                "url": "https://github.com/acme/widgets/pull/42",
                "body": "Fixes REL-9",
            }
        ]
    },
}


async def test_returns_the_raw_blame_object_on_success() -> None:
    payload = _blame_payload([{"startingLine": 1, "endingLine": 5, "commit": _COMMIT}])
    with patch.object(
        graphql_client.httpx, "AsyncClient", return_value=_mock_client(_graphql_response(payload))
    ):
        blame = await graphql_client.get_blame("token", "acme", "widgets", "main", "src/x.py")

    assert blame is not None
    assert blame["ranges"][0]["commit"]["oid"] == "abc123"


async def test_none_object_raises_graphql_error_for_unknown_ref() -> None:
    payload = {"data": {"repository": {"object": None}}}
    with (
        patch.object(
            graphql_client.httpx,
            "AsyncClient",
            return_value=_mock_client(_graphql_response(payload)),
        ),
        pytest.raises(graphql_client.GraphQLError),
    ):
        await graphql_client.get_blame("token", "acme", "widgets", "bogus-ref", "src/x.py")


async def test_none_repository_raises_graphql_error_for_unknown_repo() -> None:
    payload = {"data": {"repository": None}}
    with (
        patch.object(
            graphql_client.httpx,
            "AsyncClient",
            return_value=_mock_client(_graphql_response(payload)),
        ),
        pytest.raises(graphql_client.GraphQLError),
    ):
        await graphql_client.get_blame("token", "acme", "no-such-repo", "main", "src/x.py")


async def test_top_level_errors_array_raises_graphql_error() -> None:
    payload = {"errors": [{"message": "Field 'blame' doesn't exist"}]}
    with (
        patch.object(
            graphql_client.httpx,
            "AsyncClient",
            return_value=_mock_client(_graphql_response(payload)),
        ),
        pytest.raises(graphql_client.GraphQLError),
    ):
        await graphql_client.get_blame("token", "acme", "widgets", "main", "src/x.py")


async def test_null_blame_is_returned_as_none_not_an_error() -> None:
    payload = {"data": {"repository": {"object": {"blame": None}}}}
    with patch.object(
        graphql_client.httpx, "AsyncClient", return_value=_mock_client(_graphql_response(payload))
    ):
        blame = await graphql_client.get_blame("token", "acme", "widgets", "main", "binary.png")

    assert blame is None
