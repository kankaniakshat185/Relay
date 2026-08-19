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


async def test_list_commit_files_extracts_filenames() -> None:
    raw_commit = {
        "sha": "abc123",
        "files": [{"filename": "src/x.py"}, {"filename": "src/y.py"}],
    }
    with patch(
        "relay_api.engine.code_context.service.client.get_commit",
        new=AsyncMock(return_value=raw_commit),
    ):
        files = await service.list_commit_files("token", "acme", "widgets", "abc123")

    assert files == ["src/x.py", "src/y.py"]


async def test_list_commit_files_wraps_http_errors_as_code_context_error() -> None:
    request = httpx.Request("GET", "https://api.github.com/repos/acme/widgets/commits/abc123")
    with (
        patch(
            "relay_api.engine.code_context.service.client.get_commit",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "not found", request=request, response=httpx.Response(404, request=request)
                )
            ),
        ),
        pytest.raises(service.CodeContextError),
    ):
        await service.list_commit_files("stale-token", "acme", "widgets", "gone")


async def test_list_pr_files_extracts_filenames() -> None:
    raw_files = [{"filename": "src/x.py"}, {"filename": "src/y.py"}]
    with patch(
        "relay_api.engine.code_context.service.client.list_pull_request_files",
        new=AsyncMock(return_value=raw_files),
    ):
        files = await service.list_pr_files("token", "acme", "widgets", 42)

    assert files == ["src/x.py", "src/y.py"]


async def test_list_pr_files_wraps_http_errors_as_code_context_error() -> None:
    request = httpx.Request("GET", "https://api.github.com/repos/acme/widgets/pulls/42/files")
    with (
        patch(
            "relay_api.engine.code_context.service.client.list_pull_request_files",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "not found", request=request, response=httpx.Response(404, request=request)
                )
            ),
        ),
        pytest.raises(service.CodeContextError),
    ):
        await service.list_pr_files("stale-token", "acme", "widgets", 999)


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


def _tree(*paths_and_types: tuple[str, str]) -> dict:
    return {
        "tree": [{"path": p, "type": t, "sha": "x"} for p, t in paths_and_types],
        "truncated": False,
    }


async def test_list_files_under_filters_to_blobs_under_the_given_path() -> None:
    tree = _tree(
        ("src/payments/handler.py", "blob"),
        ("src/payments/refunds.py", "blob"),
        ("src/payments", "tree"),
        ("src/auth/login.py", "blob"),
        ("README.md", "blob"),
    )
    with patch(
        "relay_api.engine.code_context.service.client.get_tree_recursive",
        new=AsyncMock(return_value=tree),
    ):
        paths = await service._list_files_under("token", "acme", "widgets", "main", "src/payments")

    assert sorted(paths) == ["src/payments/handler.py", "src/payments/refunds.py"]


async def test_list_files_under_empty_path_matches_the_whole_repo() -> None:
    tree = _tree(("a.py", "blob"), ("b/c.py", "blob"), ("b", "tree"))
    with patch(
        "relay_api.engine.code_context.service.client.get_tree_recursive",
        new=AsyncMock(return_value=tree),
    ):
        paths = await service._list_files_under("token", "acme", "widgets", "main", "")

    assert sorted(paths) == ["a.py", "b/c.py"]


async def test_list_files_under_raises_on_truncated_tree() -> None:
    tree = {"tree": [], "truncated": True}
    with (
        patch(
            "relay_api.engine.code_context.service.client.get_tree_recursive",
            new=AsyncMock(return_value=tree),
        ),
        pytest.raises(service.CodeContextError),
    ):
        await service._list_files_under("token", "acme", "huge-monorepo", "main", "")


def _blame_result(sha: str) -> list[service.BlameRange]:
    from datetime import UTC, datetime

    return [
        service.BlameRange(
            starting_line=1,
            ending_line=5,
            commit_sha=sha,
            commit_message="msg",
            commit_url=f"https://github.com/acme/widgets/commit/{sha}",
            committed_at=datetime(2026, 1, 1, tzinfo=UTC),
            author_name="Octocat",
            author_login="octocat",
        )
    ]


async def test_get_blame_for_directory_reports_accurate_counts() -> None:
    tree = _tree(("a.py", "blob"), ("b.py", "blob"))
    with (
        patch(
            "relay_api.engine.code_context.service.client.get_tree_recursive",
            new=AsyncMock(return_value=tree),
        ),
        patch.object(
            service,
            "get_blame",
            new=AsyncMock(side_effect=lambda _t, _o, _r, _ref, path: _blame_result(f"sha-{path}")),
        ),
    ):
        result = await service.get_blame_for_directory("token", "acme", "widgets", "main", "")

    assert result.files_total == 2
    assert result.files_analyzed == 2
    assert result.files_skipped == 0
    assert {f.path for f in result.files} == {"a.py", "b.py"}


async def test_get_blame_for_directory_tolerates_one_failing_file() -> None:
    tree = _tree(("good.py", "blob"), ("binary.png", "blob"))

    async def _fake_get_blame(_token, _owner, _repo, _ref, path):
        if path == "binary.png":
            raise service.CodeContextError("no blame data — binary file")
        return _blame_result("sha-good")

    with (
        patch(
            "relay_api.engine.code_context.service.client.get_tree_recursive",
            new=AsyncMock(return_value=tree),
        ),
        patch.object(service, "get_blame", new=AsyncMock(side_effect=_fake_get_blame)),
    ):
        result = await service.get_blame_for_directory("token", "acme", "widgets", "main", "")

    assert result.files_total == 2
    assert result.files_analyzed == 1
    assert result.files_skipped == 1
    assert [f.path for f in result.files] == ["good.py"]


async def test_get_blame_for_directory_caps_at_max_files() -> None:
    many_files = _tree(
        *[(f"file{i}.py", "blob") for i in range(service._MAX_FILES_PER_DIRECTORY + 10)]
    )
    with (
        patch(
            "relay_api.engine.code_context.service.client.get_tree_recursive",
            new=AsyncMock(return_value=many_files),
        ),
        patch.object(
            service,
            "get_blame",
            new=AsyncMock(side_effect=lambda _t, _o, _r, _ref, path: _blame_result(f"sha-{path}")),
        ),
    ):
        result = await service.get_blame_for_directory("token", "acme", "widgets", "main", "")

    assert result.files_total == service._MAX_FILES_PER_DIRECTORY + 10
    assert result.files_analyzed == service._MAX_FILES_PER_DIRECTORY
    assert result.files_skipped == 10
