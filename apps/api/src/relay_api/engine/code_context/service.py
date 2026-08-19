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

from datetime import datetime
from typing import Any

import httpx

from relay_api.connectors.github import client, graphql_client
from relay_api.engine.code_context.schemas import (
    AssociatedPullRequest,
    BlameRange,
    DirectoryEntry,
    RepoSummary,
)

_REPO_LIMIT = 30


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
