"""Live, read-only access to a user's GitHub repo structure and blame data
— the one engine module that exists purely to satisfy ADR 0005's "only
engine talks to connectors" rule for `features/archaeology` and
`features/who_to_ask`, which both need identical repo/file/blame access
and must not import each other or reach into `connectors/` themselves.

Deliberately no correlation or ranking logic here — that's each feature's
own job (Jira ticket-key extraction, Slack correlation, scoring). This
module only fetches and shapes what GitHub itself returns.

Nothing here touches the database: every function is a live call against
GitHub, made fresh on every request — there's nothing to ingest ahead of
time (see the ADR for this phase).
"""

import asyncio
from datetime import datetime
from typing import Any

import httpx

from relay_api.connectors.github import client, graphql_client
from relay_api.engine.code_context.schemas import (
    AssociatedPullRequest,
    BlameRange,
    DirectoryBlame,
    DirectoryEntry,
    FileBlame,
    RepoSummary,
)

_REPO_LIMIT = 30

# Bounds on whole-directory blame: a real GraphQL call per file, so both
# numbers trade off latency against how complete an answer a large
# directory gets — NOT a GitHub rate-limit concern. A single blame call
# costs ~1 point against the 5,000-points/hour GraphQL budget (no
# paginated connections beyond `first: 1` on the PR lookup), so even
# `_MAX_FILES_PER_DIRECTORY = 500` only spends ~10% of that budget in one
# request; `_BLAME_CONCURRENCY = 25` is still well under GitHub's
# ~100-concurrent secondary-rate-limit guidance. ~20 sequential rounds
# (500 / 25) is the real cost — measured in the single-digit seconds for
# a typical repo (confirmed live at the 100-file setting before this was
# raised), not a risk of hitting a wall. One slow/broken file can't take
# the batch down either: `asyncio.gather(..., return_exceptions=True)`
# below catches anything, including a raw timeout `get_blame` doesn't
# itself wrap.
_MAX_FILES_PER_DIRECTORY = 500
_BLAME_CONCURRENCY = 25


class CodeContextError(Exception):
    """A live GitHub call in this module failed — unknown repository,
    unknown ref, a file with no blame data (binary, empty, missing path),
    or any other rejected request (e.g. a 401 from an access token GitHub
    itself considers invalid). The caller (a feature router) turns this
    into a clean 4xx rather than a raw 500 or, worse, an unhandled
    exception that never makes it back to the client at all — found live
    when `list_repos` had no error handling and a request with a
    genuinely expired token just failed silently in the browser (Phase 2
    retro)."""


async def list_repos(access_token: str) -> list[RepoSummary]:
    try:
        repos = await client.list_recent_repos(access_token, limit=_REPO_LIMIT)
    except httpx.HTTPStatusError as exc:
        raise CodeContextError(f"Could not list repos: {exc}") from exc

    return [
        RepoSummary(
            owner=repo["owner"]["login"],
            name=repo["name"],
            full_name=repo["full_name"],
            default_branch=repo["default_branch"],
        )
        for repo in repos
    ]


async def list_directory(
    access_token: str, owner: str, repo: str, path: str = ""
) -> list[DirectoryEntry]:
    try:
        entries = await client.list_directory_contents(access_token, owner, repo, path)
    except httpx.HTTPStatusError as exc:
        raise CodeContextError(f"Could not list {owner}/{repo}/{path}: {exc}") from exc

    return [
        DirectoryEntry(name=entry["name"], path=entry["path"], type=entry["type"])
        for entry in entries
        if entry["type"] in ("file", "dir")
    ]


async def list_commit_files(access_token: str, owner: str, repo: str, sha: str) -> list[str]:
    """Which files a single commit touched — ingestion never captured
    this (ADR 0010: no diffs, no file paths), so the ticket/PR-first
    search entry point (ADR 0015) resolves it live, only for the handful
    of commits a search actually matched."""
    try:
        commit = await client.get_commit(access_token, owner, repo, sha)
    except httpx.HTTPStatusError as exc:
        raise CodeContextError(f"Could not fetch commit {owner}/{repo}@{sha}: {exc}") from exc

    return [f["filename"] for f in commit.get("files", [])]


async def list_pr_files(access_token: str, owner: str, repo: str, pr_number: int) -> list[str]:
    """Same as `list_commit_files`, for a pull request."""
    try:
        files = await client.list_pull_request_files(access_token, owner, repo, pr_number)
    except httpx.HTTPStatusError as exc:
        raise CodeContextError(
            f"Could not fetch files for {owner}/{repo}#{pr_number}: {exc}"
        ) from exc

    return [f["filename"] for f in files]


def _to_blame_range(
    raw_range: dict[str, Any], pull_request: AssociatedPullRequest | None
) -> BlameRange:
    commit = raw_range["commit"]
    author = commit.get("author") or {}
    return BlameRange(
        starting_line=raw_range["startingLine"],
        ending_line=raw_range["endingLine"],
        commit_sha=commit["oid"],
        commit_message=commit["message"],
        commit_url=commit["url"],
        committed_at=datetime.fromisoformat(commit["committedDate"].replace("Z", "+00:00")),
        author_name=author.get("name"),
        author_login=(author.get("user") or {}).get("login"),
        pull_request=pull_request,
    )


async def get_blame(
    access_token: str, owner: str, repo: str, ref: str, path: str
) -> list[BlameRange]:
    try:
        raw_blame = await graphql_client.get_blame(access_token, owner, repo, ref, path)
    except (graphql_client.GraphQLError, httpx.HTTPStatusError) as exc:
        raise CodeContextError(str(exc)) from exc

    if raw_blame is None:
        raise CodeContextError(
            f"No blame data for {owner}/{repo}@{ref}:{path} — binary, empty, or missing file"
        )

    ranges: list[BlameRange] = []
    for raw_range in raw_blame["ranges"]:
        pr_nodes = raw_range["commit"].get("associatedPullRequests", {}).get("nodes", [])
        pull_request = (
            AssociatedPullRequest(
                number=pr_nodes[0]["number"],
                title=pr_nodes[0]["title"],
                url=pr_nodes[0]["url"],
                body=pr_nodes[0].get("body") or "",
            )
            if pr_nodes
            else None
        )
        ranges.append(_to_blame_range(raw_range, pull_request))

    return ranges


async def _list_files_under(
    access_token: str, owner: str, repo: str, ref: str, path: str
) -> list[str]:
    """Every file (not directory) path under `path`, via one recursive
    tree call rather than walking subdirectories one `list_directory`
    call at a time. `path == ""` means the whole repo."""
    try:
        tree = await client.get_tree_recursive(access_token, owner, repo, ref)
    except httpx.HTTPStatusError as exc:
        raise CodeContextError(f"Could not list tree for {owner}/{repo}@{ref}: {exc}") from exc

    if tree.get("truncated"):
        raise CodeContextError(
            f"{owner}/{repo} is too large to browse recursively — pick a more specific directory"
        )

    prefix = f"{path}/" if path else ""
    return [
        entry["path"]
        for entry in tree.get("tree", [])
        if entry["type"] == "blob" and entry["path"].startswith(prefix)
    ]


async def get_blame_for_directory(
    access_token: str, owner: str, repo: str, ref: str, path: str
) -> DirectoryBlame:
    """Blames every file under `path`, concurrently and capped
    (`_MAX_FILES_PER_DIRECTORY`, `_BLAME_CONCURRENCY`). A single file's
    blame failing (binary, too large, deleted mid-request) doesn't fail
    the whole directory — it's counted in `files_skipped` instead, same
    "skip it, keep going, report it honestly" discipline as Slack's
    per-channel indexing tolerance (Phase 1)."""
    all_paths = await _list_files_under(access_token, owner, repo, ref, path)
    files_total = len(all_paths)
    capped_paths = all_paths[:_MAX_FILES_PER_DIRECTORY]

    semaphore = asyncio.Semaphore(_BLAME_CONCURRENCY)

    async def _blame_one(file_path: str) -> FileBlame:
        async with semaphore:
            ranges = await get_blame(access_token, owner, repo, ref, file_path)
            return FileBlame(path=file_path, ranges=ranges)

    results = await asyncio.gather(*(_blame_one(p) for p in capped_paths), return_exceptions=True)

    files = [r for r in results if isinstance(r, FileBlame)]
    files_analyzed = len(files)
    files_skipped = files_total - files_analyzed

    return DirectoryBlame(
        files=files,
        files_total=files_total,
        files_analyzed=files_analyzed,
        files_skipped=files_skipped,
    )
