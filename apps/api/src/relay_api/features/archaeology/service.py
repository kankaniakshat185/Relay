"""Traces why a piece of code exists: git blame → the commit → its
originating PR → a linked Jira ticket → related Slack discussion at the
time (plan.md §3). Blame/browsing come from `engine.code_context` (live
GitHub calls); the correlation across Jira/Slack is this feature's own
job, reusing Phase 1's hybrid search (`engine.indexing.service.search`)
rather than building new retrieval logic.

Scope cut, documented not silent: single-file only. Aggregating blame
across every file in a directory ("module" level, per plan.md's wording)
means one blame call per file — real added cost, left for a later pass.
"""

import re
from collections import defaultdict
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors import service as connector_service
from relay_api.engine.code_context import service as code_context_service
from relay_api.engine.indexing.service import search as engine_search
from relay_api.features.archaeology.schemas import (
    ArchaeologyResponse,
    CommitEntry,
    DirectoryEntry,
    LineRange,
    PullRequestRef,
    RelatedSlackMessage,
    RepoOption,
)

if TYPE_CHECKING:
    from relay_api.engine.code_context.schemas import BlameRange

# Matches the common Jira key shape (PROJECT-123). Also matches some
# non-ticket strings that happen to look the same (e.g. "UTF-8") — a known,
# accepted false-positive rate rather than a fully-solved NLP problem;
# see the phase 2 retro.
_TICKET_KEY_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")

_RELATED_SLACK_LIMIT = 3


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


def _collapse_by_commit(ranges: list["BlameRange"]) -> list[tuple["BlameRange", list[LineRange]]]:
    """One entry per distinct commit, most recently committed first — a
    commit that wrote most of the file shows up once with several line
    ranges, not once per range."""
    representative: dict[str, BlameRange] = {}
    line_ranges: dict[str, list[LineRange]] = defaultdict(list)
    for r in ranges:
        representative.setdefault(r.commit_sha, r)
        line_ranges[r.commit_sha].append(LineRange(start=r.starting_line, end=r.ending_line))

    commits = sorted(representative.values(), key=lambda r: r.committed_at, reverse=True)
    return [(c, line_ranges[c.commit_sha]) for c in commits]


def _extract_ticket_key(commit_message: str, pr: PullRequestRef | None, pr_body: str) -> str | None:
    for text in (commit_message, pr.title if pr else "", pr_body):
        match = _TICKET_KEY_PATTERN.search(text)
        if match:
            return match.group(0)
    return None


async def _jira_ticket_url(db: AsyncSession, user: User, ticket_key: str) -> str | None:
    credential = await connector_service.get_credential(db, user.id, "jira")
    if credential is None:
        return None
    site_url = credential.external_account_label.rstrip("/")
    return f"{site_url}/browse/{ticket_key}"


async def _related_slack(
    db: AsyncSession, user: User, query: str | None
) -> list[RelatedSlackMessage]:
    if not query:
        return []
    items = await engine_search(db, user.id, query, sources=["slack"], limit=_RELATED_SLACK_LIMIT)
    return [
        RelatedSlackMessage(
            title=item.title,
            url=item.url,
            excerpt=" ".join(item.body.split())[:200],
            occurred_at=item.occurred_at,
        )
        for item in items
    ]


async def trace(
    db: AsyncSession, user: User, *, owner: str, repo: str, ref: str, path: str
) -> ArchaeologyResponse:
    token = await connector_service.get_required_access_token(db, user.id, "github")
    blame_ranges = await code_context_service.get_blame(token, owner, repo, ref, path)

    timeline = []
    for commit, line_ranges in _collapse_by_commit(blame_ranges):
        pr = (
            PullRequestRef(
                number=commit.pull_request.number,
                title=commit.pull_request.title,
                url=commit.pull_request.url,
            )
            if commit.pull_request
            else None
        )
        pr_body = commit.pull_request.body if commit.pull_request else ""
        ticket_key = _extract_ticket_key(commit.commit_message, pr, pr_body)
        ticket_url = await _jira_ticket_url(db, user, ticket_key) if ticket_key else None
        related_slack = await _related_slack(db, user, ticket_key or (pr.title if pr else None))

        timeline.append(
            CommitEntry(
                sha=commit.commit_sha,
                short_sha=commit.commit_sha[:7],
                message=commit.commit_message,
                author=commit.author_login or commit.author_name,
                committed_at=commit.committed_at,
                url=commit.commit_url,
                line_ranges=line_ranges,
                pull_request=pr,
                jira_ticket_key=ticket_key,
                jira_ticket_url=ticket_url,
                related_slack=related_slack,
            )
        )

    return ArchaeologyResponse(timeline=timeline)
