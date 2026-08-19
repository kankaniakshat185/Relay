"""Resolves a free-text query (a ticket key, a keyword) to candidate
GitHub commits/PRs and the files each one touched — the ticket/PR-first
entry point (ADR 0015), an alternative to browsing the repo tree by hand
in `RepoFilePicker`.

Two distinct steps, each already owned elsewhere, coordinated here rather
than duplicated in both features (ADR 0005):
  1. A DB text search over already-ingested GitHub items
     (`engine.indexing.service.search`) — cheap, no live API call, finds
     *which* commits/PRs matched.
  2. A live GitHub call per match to resolve its changed files
     (`engine.code_context.service.list_commit_files`/`list_pr_files`) —
     ingestion never captured file paths (ADR 0010), so this is where
     that gap gets filled in, on demand, only for the handful of items a
     search actually matched, never during ingestion itself.

Neither `engine/code_context` (deliberately DB-free) nor
`engine/correlation` (deliberately live-call-free, DB text search only)
was a clean fit for a function that needs both — see ADR 0015.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.engine.code_context.service import (
    CodeContextError,
    list_commit_files,
    list_pr_files,
)
from relay_api.engine.code_search.schemas import FileMatch
from relay_api.engine.indexing.service import search as engine_search

_SEARCH_CANDIDATE_LIMIT = 5


async def find_files_for_query(
    db: AsyncSession,
    access_token: str,
    user_id: uuid.UUID,
    query: str,
    *,
    limit: int = _SEARCH_CANDIDATE_LIMIT,
) -> list[FileMatch]:
    if not query:
        return []

    hits = await engine_search(db, user_id, query, sources=["github"], limit=limit)

    matches: list[FileMatch] = []
    for item in hits:
        repo_full_name = item.extra.get("repo")
        if not repo_full_name or "/" not in repo_full_name:
            # Every GitHub-sourced item is normalized with `extra.repo`
            # set (see `connectors/github/normalize.py`) — this only
            # guards against a malformed/legacy row, not an expected path.
            continue
        owner, repo = repo_full_name.split("/", 1)

        try:
            if item.source_type == "commit":
                # `external_id` is the commit's full SHA; `extra["sha"]`
                # is truncated to 7 characters for display and isn't
                # guaranteed unique enough for a live lookup.
                files = await list_commit_files(access_token, owner, repo, item.external_id)
                matches.append(
                    FileMatch(
                        kind="commit",
                        repo=repo_full_name,
                        title=item.title,
                        url=item.url,
                        occurred_at=item.occurred_at,
                        files=files,
                        sha=item.external_id,
                    )
                )
            elif item.source_type == "pull_request":
                pr_number = item.extra.get("number")
                if pr_number is None:
                    continue
                files = await list_pr_files(access_token, owner, repo, pr_number)
                matches.append(
                    FileMatch(
                        kind="pull_request",
                        repo=repo_full_name,
                        title=item.title,
                        url=item.url,
                        occurred_at=item.occurred_at,
                        files=files,
                        pr_number=pr_number,
                    )
                )
            # Other GitHub source_types (none exist yet) are silently
            # skipped rather than raising — this function's job is "show
            # what could be resolved," not "fail if one candidate can't."
        except CodeContextError:
            # One bad candidate (a force-pushed-away commit, a PR closed
            # and later deleted) shouldn't fail the whole search — same
            # "skip it, keep going" discipline as directory blame
            # (`engine.code_context.service.get_blame_for_directory`).
            continue

    return matches
