"""`get_tree_recursive` — the one thing worth testing here in isolation
is that the raw response (including the `truncated` flag) is passed
through untouched; shaping/filtering is `engine/code_context`'s job."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from relay_api.connectors.github import client


def _mock_client(response: httpx.Response) -> MagicMock:
    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    mock.get = AsyncMock(return_value=response)
    return mock


def _tree_response(body: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://api.github.com/repos/acme/widgets/git/trees/main")
    return httpx.Response(status_code, json=body, request=request)


async def test_returns_the_raw_tree_response() -> None:
    body = {
        "tree": [
            {"path": "src/x.py", "type": "blob", "sha": "abc"},
            {"path": "src", "type": "tree", "sha": "def"},
        ],
        "truncated": False,
    }
    with patch.object(client.httpx, "AsyncClient", return_value=_mock_client(_tree_response(body))):
        result = await client.get_tree_recursive("token", "acme", "widgets", "main")

    assert result == body


async def test_truncated_flag_is_passed_through_for_the_caller_to_decide() -> None:
    body = {"tree": [], "truncated": True}
    with patch.object(client.httpx, "AsyncClient", return_value=_mock_client(_tree_response(body))):
        result = await client.get_tree_recursive("token", "acme", "huge-monorepo", "main")

    assert result["truncated"] is True


def _response(body: dict | list, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://api.github.com/repos/acme/widgets")
    return httpx.Response(status_code, json=body, request=request)


async def test_get_commit_returns_the_raw_commit_response() -> None:
    body = {"sha": "abc123", "files": [{"filename": "src/x.py"}]}
    with patch.object(client.httpx, "AsyncClient", return_value=_mock_client(_response(body))):
        result = await client.get_commit("token", "acme", "widgets", "abc123")

    assert result == body


async def test_list_pull_request_files_returns_the_raw_files_response() -> None:
    body = [{"filename": "src/x.py"}, {"filename": "src/y.py"}]
    with patch.object(client.httpx, "AsyncClient", return_value=_mock_client(_response(body))):
        result = await client.list_pull_request_files("token", "acme", "widgets", 42)

    assert result == body


async def test_list_pr_reviews_returns_the_raw_reviews_response() -> None:
    body = [{"id": 1, "state": "APPROVED", "body": "LGTM"}]
    with patch.object(client.httpx, "AsyncClient", return_value=_mock_client(_response(body))):
        result = await client.list_pr_reviews("token", "acme", "widgets", 42)

    assert result == body


async def test_list_pr_review_comments_returns_the_raw_comments_response() -> None:
    body = [{"id": 1, "path": "src/x.py", "body": "Nit: rename this"}]
    with patch.object(client.httpx, "AsyncClient", return_value=_mock_client(_response(body))):
        result = await client.list_pr_review_comments("token", "acme", "widgets", 42)

    assert result == body
