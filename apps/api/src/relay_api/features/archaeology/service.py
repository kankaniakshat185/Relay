"""Traces why a piece of code exists: git blame → the commit → its
originating PR → a linked Jira ticket → related Slack discussion at the
time (plan.md §3). The actual timeline-building — blame/browsing from
`engine.code_context`, correlation from `engine.correlation` — lives in
`engine.timeline` (see that module's docstring for why); this service is
now the thin feature-level wrapper: resolve the access token, call the
engine, done.

Works on a single file or a whole directory (`target_type`) — directory
mode flattens every matched file's blame ranges before collapsing by
commit, so a PR that touched 5 files in the module is one timeline entry,
not 5 (see ADR 0011 and `engine.code_context.get_blame_for_directory`).
"""

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors import service as connector_service
from relay_api.engine.code_context import service as code_context_service
from relay_api.engine.code_search import service as code_search_service
from relay_api.engine.timeline import service as timeline_service
from relay_api.engine.timeline.schemas import TimelineResult
from relay_api.features.archaeology.schemas import (
    DirectoryEntry,
    FileSearchMatch,
    RepoOption,
)


async def list_repos(db: AsyncSession, user: User) -> list[RepoOption]:
    token = await connector_service.get_required_access_token(db, user.id, "github")
    repos = await code_context_service.list_repos(token)
    return [RepoOption(**vars(r)) for r in repos]


async def browse(
    db: AsyncSession, user: User, owner: str, repo: str, path: str = ""
) -> list[DirectoryEntry]:
    token = await connector_service.get_required_access_token(db, user.id, "github")
    entries = await code_context_service.list_directory(token, owner, repo, path)
    return [DirectoryEntry(**vars(e)) for e in entries]


async def search_files(db: AsyncSession, user: User, query: str) -> list[FileSearchMatch]:
    """The ticket/PR-first entry point (ADR 0015) — an alternative to
    `browse` above for landing on a file to trace."""
    token = await connector_service.get_required_access_token(db, user.id, "github")
    matches = await code_search_service.find_files_for_query(db, token, user.id, query)
    return [FileSearchMatch(**vars(m)) for m in matches]


async def trace(
    db: AsyncSession,
    user: User,
    *,
    owner: str,
    repo: str,
    ref: str,
    path: str,
    target_type: Literal["file", "directory"] = "file",
) -> TimelineResult:
    token = await connector_service.get_required_access_token(db, user.id, "github")
    return await timeline_service.build_timeline(
        db,
        user.id,
        access_token=token,
        owner=owner,
        repo=repo,
        ref=ref,
        path=path,
        target_type=target_type,
    )
