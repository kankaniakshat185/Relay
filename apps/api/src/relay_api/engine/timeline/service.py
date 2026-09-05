"""Builds a correlated commit timeline for a file or directory: git blame
→ each commit → its originating PR → a linked Jira ticket → related Slack
discussion at the time → similar past issues → the PR's own code-review
commentary. Blame/browsing come from `engine.code_context` (live GitHub
calls); ticket/Slack/similar-issue correlation comes from
`engine.correlation`.

Originally `features/archaeology/service.py`'s `trace()` in full — moved
here once a second feature (incident correlation) needed the exact same
"file → correlated commit history" capability, not a new implementation
of it. `features/archaeology` now calls `build_timeline` and shapes the
result as its own response; `features/incident_correlation` calls it
too, then filters the timeline to a time window instead of showing all
of it. Same `engine/correlation`/`engine/synthesis` extraction pattern —
see ADR 0005 and the ADR documenting this specific move.
"""

import uuid
from collections import defaultdict
from typing import TYPE_CHECKING, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.engine.code_context import service as code_context_service
from relay_api.engine.correlation import service as correlation_service
from relay_api.engine.timeline.schemas import (
    LineRange,
    PullRequestRef,
    RelatedItem,
    ReviewComment,
    TimelineEntry,
    TimelineResult,
)

if TYPE_CHECKING:
    from relay_api.engine.code_context.schemas import BlameRange


def _collapse_by_commit(
    ranges_with_paths: list[tuple[str, "BlameRange"]],
) -> list[tuple["BlameRange", list[LineRange], list[str]]]:
    """One entry per distinct commit, most recently committed first — a
    commit that wrote most of a file shows up once with several line
    ranges, not once per range. Tracks both line ranges (meaningful only
    in single-file mode) and every distinct file touched (meaningful in
    directory mode, where the same commit can appear across several of
    the flattened per-file blame results and must still collapse to one
    entry) — `build_timeline` decides which one the response actually uses."""
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


async def build_timeline(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    access_token: str,
    owner: str,
    repo: str,
    ref: str,
    path: str,
    target_type: Literal["file", "directory"] = "file",
) -> TimelineResult:
    """`access_token` is resolved by the caller (same convention as every
    other `engine/` module — this layer never talks to `connectors/*`
    itself)."""
    if target_type == "file":
        blame_ranges = await code_context_service.get_blame(access_token, owner, repo, ref, path)
        ranges_with_paths = [(path, r) for r in blame_ranges]
        files_total = files_analyzed = 1
        files_skipped = 0
    else:
        directory_blame = await code_context_service.get_blame_for_directory(
            access_token, owner, repo, ref, path
        )
        ranges_with_paths = [
            (file_blame.path, r) for file_blame in directory_blame.files for r in file_blame.ranges
        ]
        files_total = directory_blame.files_total
        files_analyzed = directory_blame.files_analyzed
        files_skipped = directory_blame.files_skipped

    # Fetched once, not once per commit — the credential doesn't change
    # mid-request, and a timeline can have many entries (directory mode).
    jira_site_url = await correlation_service.get_jira_site_url(db, user_id)

    timeline = []
    for commit, line_ranges, files_touched in _collapse_by_commit(ranges_with_paths):
        review_items = (
            await correlation_service.find_review_comments_for_pr(
                db, user_id, owner, repo, commit.pull_request.number
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
            db, user_id, ticket_key or (pr.title if pr else None), sources=["slack"]
        )
        related_slack = [RelatedItem(**vars(m)) for m in related_slack_msgs]
        similar_issue_msgs = (
            await correlation_service.find_similar_jira_issues(db, user_id, ticket_key)
            if ticket_key
            else []
        )
        similar_issues = [RelatedItem(**vars(m)) for m in similar_issue_msgs]

        timeline.append(
            TimelineEntry(
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

    return TimelineResult(
        timeline=timeline,
        files_total=files_total,
        files_analyzed=files_analyzed,
        files_skipped=files_skipped,
    )
