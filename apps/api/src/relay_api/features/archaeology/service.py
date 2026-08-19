"""Traces why a piece of code exists: git blame → the commit → its
originating PR → a linked Jira ticket → related Slack discussion at the
time (plan.md §3). Blame/browsing come from `engine.code_context` (live
GitHub calls); the Jira/Slack correlation, and the PR's own code-review
commentary (ADR 0016), come from `engine.correlation` — shared with
`features/who_to_ask`, which needs the exact same
ticket-key-to-Slack-discussion logic (ADR 0012).

Works on a single file or a whole directory (`target_type`) — directory
mode flattens every matched file's blame ranges before collapsing by
commit, so a PR that touched 5 files in the module is one timeline entry,
not 5 (see ADR 0011 and `engine.code_context.get_blame_for_directory`).
"""

from collections import defaultdict
from typing import TYPE_CHECKING, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors import service as connector_service
from relay_api.engine.code_context import service as code_context_service
from relay_api.engine.code_search import service as code_search_service
from relay_api.engine.correlation import service as correlation_service
from relay_api.features.archaeology.schemas import (
    ArchaeologyResponse,
    CommitEntry,
    DirectoryEntry,
    FileSearchMatch,
    LineRange,
    PullRequestRef,
    RelatedItem,
    RepoOption,
    ReviewComment,
)

if TYPE_CHECKING:
    from relay_api.engine.code_context.schemas import BlameRange


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


def _collapse_by_commit(
    ranges_with_paths: list[tuple[str, "BlameRange"]],
) -> list[tuple["BlameRange", list[LineRange], list[str]]]:
    """One entry per distinct commit, most recently committed first — a
    commit that wrote most of a file shows up once with several line
    ranges, not once per range. Tracks both line ranges (meaningful only
    in single-file mode) and every distinct file touched (meaningful in
    directory mode, where the same commit can appear across several of
    the flattened per-file blame results and must still collapse to one
    entry) — `trace()` decides which one the response actually uses."""
    representative: dict[str, BlameRange] = {}
    line_ranges: dict[str, list[LineRange]] = defaultdict(list)
    files_touched: dict[str, list[str]] = defaultdict(list)
    for file_path, r in ranges_with_paths:
        representative.setdefault(r.commit_sha, r)
        line_ranges[r.commit_sha].append(LineRange(start=r.starting_line, end=r.ending_line))
        if file_path not in files_touched[r.commit_sha]:
            files_touched[r.commit_sha].append(file_path)

    commits = sorted(representative.values(), key=lambda r: r.committed_at, reverse=True)
    return [(c, line_ranges[c.commit_sha], files_touched[c.commit_sha]) for c in commits]


async def trace(
    db: AsyncSession,
    user: User,
    *,
    owner: str,
    repo: str,
    ref: str,
    path: str,
    target_type: Literal["file", "directory"] = "file",
) -> ArchaeologyResponse:
    token = await connector_service.get_required_access_token(db, user.id, "github")

    if target_type == "file":
        blame_ranges = await code_context_service.get_blame(token, owner, repo, ref, path)
        ranges_with_paths = [(path, r) for r in blame_ranges]
        files_total = files_analyzed = 1
        files_skipped = 0
    else:
        directory_blame = await code_context_service.get_blame_for_directory(
            token, owner, repo, ref, path
        )
        ranges_with_paths = [
            (file_blame.path, r) for file_blame in directory_blame.files for r in file_blame.ranges
        ]
        files_total = directory_blame.files_total
        files_analyzed = directory_blame.files_analyzed
        files_skipped = directory_blame.files_skipped

    # Fetched once, not once per commit — the credential doesn't change
    # mid-request, and a timeline can now have many entries (directory mode).
    jira_site_url = await correlation_service.get_jira_site_url(db, user.id)

    timeline = []
    for commit, line_ranges, files_touched in _collapse_by_commit(ranges_with_paths):
        review_items = (
            await correlation_service.find_review_comments_for_pr(
                db, user.id, owner, repo, commit.pull_request.number
            )
            if commit.pull_request
            else []
        )
        review_comments = [ReviewComment(**vars(r)) for r in review_items]
        pr = (
            PullRequestRef(
                number=commit.pull_request.number,
                title=commit.pull_request.title,
                url=commit.pull_request.url,
                has_unresolved_review=correlation_service.has_unresolved_concerns(review_items),
            )
            if commit.pull_request
            else None
        )
        pr_body = commit.pull_request.body if commit.pull_request else ""
        ticket_key = correlation_service.extract_ticket_key(
            commit.commit_message, pr.title if pr else "", pr_body
        )
        ticket_url = (
            correlation_service.build_jira_ticket_url(jira_site_url, ticket_key)
            if ticket_key
            else None
        )
        related_slack_msgs = await correlation_service.find_related(
            db, user.id, ticket_key or (pr.title if pr else None), sources=["slack"]
        )
        related_slack = [RelatedItem(**vars(m)) for m in related_slack_msgs]
        similar_issue_msgs = (
            await correlation_service.find_similar_jira_issues(db, user.id, ticket_key)
            if ticket_key
            else []
        )
        similar_issues = [RelatedItem(**vars(m)) for m in similar_issue_msgs]

        timeline.append(
            CommitEntry(
                sha=commit.commit_sha,
                short_sha=commit.commit_sha[:7],
                message=commit.commit_message,
                author=commit.author_login or commit.author_name,
                committed_at=commit.committed_at,
                url=commit.commit_url,
                line_ranges=line_ranges if target_type == "file" else [],
                files_touched=files_touched,
                pull_request=pr,
                jira_ticket_key=ticket_key,
                jira_ticket_url=ticket_url,
                related_slack=related_slack,
                similar_issues=similar_issues,
                review_comments=review_comments,
            )
        )

    return ArchaeologyResponse(
        timeline=timeline,
        files_total=files_total,
        files_analyzed=files_analyzed,
        files_skipped=files_skipped,
    )
