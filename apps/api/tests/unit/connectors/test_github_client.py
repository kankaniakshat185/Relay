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


async def test_list_workflow_runs_unwraps_the_workflow_runs_key() -> None:
    # Unlike every other list endpoint here, Actions wraps its list in an
    # envelope object (`{"total_count": N, "workflow_runs": [...]}`), not
    # a bare array — this is the one thing worth testing in isolation.
    body = {
        "total_count": 2,
        "workflow_runs": [{"id": 1, "name": "CI"}, {"id": 2, "name": "CI"}],
    }
    with patch.object(client.httpx, "AsyncClient", return_value=_mock_client(_response(body))):
        result = await client.list_workflow_runs("token", "acme", "widgets")

    assert result == body["workflow_runs"]


async def test_list_workflow_runs_defaults_to_empty_list_when_key_missing() -> None:
    with patch.object(
        client.httpx, "AsyncClient", return_value=_mock_client(_response({"total_count": 0}))
    ):
        result = await client.list_workflow_runs("token", "acme", "widgets")

    assert result == []


async def test_get_workflow_run_attempt_returns_the_raw_response() -> None:
    body = {"id": 1, "run_attempt": 1, "conclusion": "failure"}
    with patch.object(client.httpx, "AsyncClient", return_value=_mock_client(_response(body))):
        result = await client.get_workflow_run_attempt("token", "acme", "widgets", 1, 1)

    assert result == body


async def test_get_file_content_decodes_the_base64_body() -> None:
    import base64

    body = {
        "type": "file",
        "content": base64.b64encode(b"# ADR 0001: Use Postgres\n\nBecause it's boring.").decode(),
    }
    with patch.object(client.httpx, "AsyncClient", return_value=_mock_client(_response(body))):
        result = await client.get_file_content("token", "acme", "widgets", "docs/adr/0001.md")

    assert result == "# ADR 0001: Use Postgres\n\nBecause it's boring."


async def test_get_file_content_returns_none_for_a_404() -> None:
    with patch.object(
        client.httpx, "AsyncClient", return_value=_mock_client(_response({}, status_code=404))
    ):
        result = await client.get_file_content("token", "acme", "widgets", "docs/adr")

    assert result is None


async def test_get_file_content_returns_none_for_a_directory() -> None:
    # GitHub returns a bare list, not a `{"type": "file", ...}` object,
    # when `path` points at a directory instead of a file.
    with patch.object(client.httpx, "AsyncClient", return_value=_mock_client(_response([]))):
        result = await client.get_file_content("token", "acme", "widgets", "docs/adr")

    assert result is None


async def test_get_latest_commit_for_path_returns_the_first_result() -> None:
    body = [
        {"sha": "newest", "commit": {"author": {"date": "2026-01-01T00:00:00Z"}}},
        {"sha": "older", "commit": {"author": {"date": "2025-01-01T00:00:00Z"}}},
    ]
    with patch.object(client.httpx, "AsyncClient", return_value=_mock_client(_response(body))):
        result = await client.get_latest_commit_for_path(
            "token", "acme", "widgets", "docs/adr/0001.md"
        )

    assert result is not None
    assert result["sha"] == "newest"


async def test_get_latest_commit_for_path_returns_none_when_no_commits() -> None:
    with patch.object(client.httpx, "AsyncClient", return_value=_mock_client(_response([]))):
        result = await client.get_latest_commit_for_path(
            "token", "acme", "widgets", "docs/adr/gone.md"
        )

    assert result is None
