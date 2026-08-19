"""`engine/code_search` coordinates a DB text search
(`engine.indexing.service.search`, mocked here as `engine_search`) with
live file resolution (`engine.code_context.service.list_commit_files`/
`list_pr_files`, mocked here as-is) — same boundary-mocking style as
`test_correlation.py`."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from relay_api.engine.code_context.service import CodeContextError
from relay_api.engine.code_search import service
from relay_api.engine.ingestion.models import IngestedItem


def _commit_item(repo: str, sha: str, title: str) -> IngestedItem:
    return IngestedItem(
        source="github",
        source_type="commit",
        external_id=sha,
        title=title,
        body=title,
        url=f"https://github.com/{repo}/commit/{sha}",
        author="octocat",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={"repo": repo, "sha": sha[:7]},
    )


def _pr_item(repo: str, number: int, title: str) -> IngestedItem:
    return IngestedItem(
        source="github",
        source_type="pull_request",
        external_id="99999",
        title=title,
        body=title,
        url=f"https://github.com/{repo}/pull/{number}",
        author="octocat",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={"repo": repo, "state": "open", "number": number},
    )


async def test_returns_empty_list_for_no_query() -> None:
    with patch.object(service, "engine_search", new=AsyncMock(return_value=[])) as mock_search:
        result = await service.find_files_for_query(object(), "token", uuid.uuid4(), "")

    assert result == []
    mock_search.assert_not_awaited()


async def test_resolves_a_commit_hit_to_its_changed_files() -> None:
    item = _commit_item("acme/widgets", "abc123full", "REL-42: fix retry logic")
    with (
        patch.object(service, "engine_search", new=AsyncMock(return_value=[item])),
        patch(
            "relay_api.engine.code_search.service.list_commit_files",
            new=AsyncMock(return_value=["src/x.py", "src/y.py"]),
        ) as mock_list_commit_files,
    ):
        matches = await service.find_files_for_query(object(), "token", uuid.uuid4(), "REL-42")

    assert len(matches) == 1
    match = matches[0]
    assert match.kind == "commit"
    assert match.repo == "acme/widgets"
    assert match.sha == "abc123full"  # the full external_id, not the truncated extra["sha"]
    assert match.pr_number is None
    assert match.files == ["src/x.py", "src/y.py"]
    mock_list_commit_files.assert_awaited_once_with("token", "acme", "widgets", "abc123full")


async def test_resolves_a_pull_request_hit_to_its_changed_files() -> None:
    item = _pr_item("acme/widgets", 42, "REL-42: fix retry logic")
    with (
        patch.object(service, "engine_search", new=AsyncMock(return_value=[item])),
        patch(
            "relay_api.engine.code_search.service.list_pr_files",
            new=AsyncMock(return_value=["src/x.py"]),
        ) as mock_list_pr_files,
    ):
        matches = await service.find_files_for_query(object(), "token", uuid.uuid4(), "REL-42")

    assert len(matches) == 1
    match = matches[0]
    assert match.kind == "pull_request"
    assert match.pr_number == 42
    assert match.sha is None
    assert match.files == ["src/x.py"]
    mock_list_pr_files.assert_awaited_once_with("token", "acme", "widgets", 42)


async def test_skips_a_hit_missing_repo_metadata() -> None:
    item = _commit_item("acme/widgets", "abc123", "msg")
    item.extra = {}  # malformed/legacy row, no "repo" key
    with patch.object(service, "engine_search", new=AsyncMock(return_value=[item])):
        matches = await service.find_files_for_query(object(), "token", uuid.uuid4(), "query")

    assert matches == []


async def test_one_failing_candidate_does_not_fail_the_whole_search() -> None:
    good = _commit_item("acme/widgets", "good-sha", "good commit")
    bad = _commit_item("acme/widgets", "gone-sha", "force-pushed-away commit")

    async def _fake_list_commit_files(_token, _owner, _repo, sha):
        if sha == "gone-sha":
            raise CodeContextError("commit not found")
        return ["src/x.py"]

    with (
        patch.object(service, "engine_search", new=AsyncMock(return_value=[bad, good])),
        patch(
            "relay_api.engine.code_search.service.list_commit_files",
            new=AsyncMock(side_effect=_fake_list_commit_files),
        ),
    ):
        matches = await service.find_files_for_query(object(), "token", uuid.uuid4(), "query")

    assert len(matches) == 1
    assert matches[0].sha == "good-sha"


async def test_passes_sources_and_limit_through_to_search() -> None:
    with patch.object(service, "engine_search", new=AsyncMock(return_value=[])) as mock_search:
        await service.find_files_for_query(object(), "token", uuid.uuid4(), "REL-42", limit=3)

    mock_search.assert_awaited_once()
    args = mock_search.call_args
    assert args.args[2] == "REL-42"
    assert args.kwargs["sources"] == ["github"]
    assert args.kwargs["limit"] == 3
