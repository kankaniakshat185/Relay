"""`engine/code_context` is a thin shaping layer over the GitHub connector
— these tests mock `connectors.github.client`/`graphql_client` directly
(as `features/*` never should) and check the shaping + error mapping."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from relay_api.connectors.github import graphql_client
from relay_api.engine.code_context import service


async def test_list_repos_shapes_owner_name_and_default_branch() -> None:
    raw_repos = [
        {
            "owner": {"login": "acme"},
            "name": "widgets",
            "full_name": "acme/widgets",
            "default_branch": "main",
        }
    ]
    with patch(
        "relay_api.engine.code_context.service.client.list_recent_repos",
        new=AsyncMock(return_value=raw_repos),
    ):
        repos = await service.list_repos("token")

    assert repos == [
        service.RepoSummary(
            owner="acme", name="widgets", full_name="acme/widgets", default_branch="main"
        )
    ]


async def test_list_repos_wraps_http_errors_as_code_context_error() -> None:
    # This is the exact gap that shipped without a test the first time —
    # an expired/rejected token here used to blow up as an unhandled
    # exception all the way to the client (Phase 2 retro).
    request = httpx.Request("GET", "https://api.github.com/user/repos")
    with (
        patch(
            "relay_api.engine.code_context.service.client.list_recent_repos",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "unauthorized", request=request, response=httpx.Response(401, request=request)
                )
            ),
        ),
        pytest.raises(service.CodeContextError),
    ):
        await service.list_repos("stale-token")


async def test_list_directory_filters_to_files_and_dirs_only() -> None:
    raw_entries = [
        {"name": "src", "path": "src", "type": "dir"},
        {"name": "README.md", "path": "README.md", "type": "file"},
        {"name": "weird", "path": "weird", "type": "symlink"},
    ]
    with patch(
        "relay_api.engine.code_context.service.client.list_directory_contents",
        new=AsyncMock(return_value=raw_entries),
    ):
        entries = await service.list_directory("token", "acme", "widgets")

    assert [e.name for e in entries] == ["src", "README.md"]


async def test_list_directory_wraps_http_errors_as_code_context_error() -> None:
    request = httpx.Request("GET", "https://api.github.com/repos/acme/widgets/contents/")
    with (
        patch(
            "relay_api.engine.code_context.service.client.list_directory_contents",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "not found", request=request, response=httpx.Response(404, request=request)
                )
            ),
        ),
        pytest.raises(service.CodeContextError),
    ):
        await service.list_directory("token", "acme", "does-not-exist")


async def test_get_blame_shapes_ranges_and_associated_pull_request() -> None:
    raw_blame = {
        "ranges": [
            {
                "startingLine": 1,
                "endingLine": 5,
                "commit": {
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
                },
            }
        ]
    }
    with patch(
        "relay_api.engine.code_context.service.graphql_client.get_blame",
        new=AsyncMock(return_value=raw_blame),
    ):
        ranges = await service.get_blame("token", "acme", "widgets", "main", "src/x.py")

    assert len(ranges) == 1
    r = ranges[0]
    assert r.commit_sha == "abc123"
    assert r.author_login == "octocat"
    assert r.pull_request is not None
    assert r.pull_request.number == 42
    assert r.pull_request.body == "Fixes REL-9"


async def test_get_blame_with_no_associated_pr_leaves_it_none() -> None:
    raw_blame = {
        "ranges": [
            {
                "startingLine": 1,
                "endingLine": 5,
                "commit": {
                    "oid": "abc123",
                    "message": "Fix retry logic",
                    "committedDate": "2026-01-01T00:00:00Z",
                    "url": "https://github.com/acme/widgets/commit/abc123",
                    "author": {"name": "Octocat", "user": {"login": "octocat"}},
                    "associatedPullRequests": {"nodes": []},
                },
            }
        ]
    }
    with patch(
        "relay_api.engine.code_context.service.graphql_client.get_blame",
        new=AsyncMock(return_value=raw_blame),
    ):
        ranges = await service.get_blame("token", "acme", "widgets", "main", "src/x.py")

    assert ranges[0].pull_request is None


async def test_get_blame_raises_code_context_error_when_blame_is_none() -> None:
    with (
        patch(
            "relay_api.engine.code_context.service.graphql_client.get_blame",
            new=AsyncMock(return_value=None),
        ),
        pytest.raises(service.CodeContextError),
    ):
        await service.get_blame("token", "acme", "widgets", "main", "binary.png")


async def test_get_blame_wraps_graphql_error_as_code_context_error() -> None:
    with (
        patch(
            "relay_api.engine.code_context.service.graphql_client.get_blame",
            new=AsyncMock(side_effect=graphql_client.GraphQLError("unknown ref")),
        ),
        pytest.raises(service.CodeContextError),
    ):
        await service.get_blame("token", "acme", "widgets", "bogus", "src/x.py")
