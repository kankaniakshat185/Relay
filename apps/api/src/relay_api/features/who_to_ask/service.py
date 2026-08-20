"""Given a file/module, who's worth asking about it? (plan.md §3). Blame
data comes from `engine.code_context` — same source Archaeology uses, on
purpose (ADR 0010/0011) — and the actual "who's most worth asking"
question is answered by `engine.ranking`'s two differential-tested
strategies, not decided here.

Works on a single file, a whole directory, or a pull request
(`target_type`) — directory and pull-request mode both pool every
matched file's blame ranges before deduping by commit, so a commit that
touched 3 files still counts as exactly one touch for its author, not
three (see ADR 0011). Pull-request mode ("PR Blast Radius") is the same
pooling operation as directory mode, just fed by a PR's changed-files
list (`engine.code_context.get_blame_for_pull_request`) instead of a
directory tree walk — everything downstream of the blame ranges
(dedup, ranking, correlation, reviewer ranking) is unchanged either way.

Each ranked person also gets a Jira ticket link and related Slack
discussion, via the same `engine.correlation` module Archaeology uses
(ADR 0012) — closing the "Slack discussion recency" half of plan.md's
original spec for this feature, which Phase 2 shipped without. Bounded
to **one lookup per person**, not per commit — commit lists are uncapped
and directory mode can span hundreds of files, so per-commit correlation
would scale with the wrong thing.

Reviewers (people who commented on a PR without ever committing to it)
are ranked too, not just committers (ADR 0016) — their review commentary
becomes additional `Touch`es, and `PersonScore.reviews` keeps that
contribution visibly distinct from `commits` rather than misrepresenting
a review as a commit.
"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors import service as connector_service
from relay_api.engine.code_context import service as code_context_service
from relay_api.engine.code_context.schemas import BlameRange
from relay_api.engine.code_search import service as code_search_service
from relay_api.engine.correlation import service as correlation_service
from relay_api.engine.ranking.schemas import RankedPerson, Touch
from relay_api.engine.ranking.strategies import rank_by_frequency, rank_by_recency
from relay_api.features.who_to_ask.schemas import (
    CommitSummary,
    DirectoryEntry,
    FileSearchMatch,
    PersonScore,
    RankingStrategy,
    RelatedItem,
    RepoOption,
    ReviewSummary,
    WhoToAskResponse,
)

# How many of a person's most recent commits to check for a Jira ticket
# key before giving up — bounds the work per person regardless of how
# many commits they actually have (which can now be large).
_TICKET_LOOKBACK_COMMITS = 5


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
    `browse` above for landing on a file to rank."""
    token = await connector_service.get_required_access_token(db, user.id, "github")
    matches = await code_search_service.find_files_for_query(db, token, user.id, query)
    return [FileSearchMatch(**vars(m)) for m in matches]


def _distinct_commits(ranges: list[BlameRange]) -> list[BlameRange]:
    """One entry per commit sha — a commit that touched many lines in the
    blamed file is one touch by its author, not one per line range."""
    seen: dict[str, BlameRange] = {}
    for r in ranges:
        seen.setdefault(r.commit_sha, r)
    return list(seen.values())


def _extract_ticket_key_from_recent_commits(blames: list[BlameRange]) -> str | None:
    """Checks a person's most recent commits (bounded by
    `_TICKET_LOOKBACK_COMMITS`, not all of them) for the first extractable
    Jira ticket key — same commit-message → PR-title → PR-body fallback
    chain Archaeology uses per commit, applied here per person instead."""
    recent = sorted(blames, key=lambda r: r.committed_at, reverse=True)[:_TICKET_LOOKBACK_COMMITS]
    for r in recent:
        pr = r.pull_request
        key = correlation_service.extract_ticket_key(
            r.commit_message, pr.title if pr else "", pr.body if pr else ""
        )
        if key:
            return key
    return None


async def rank(
    db: AsyncSession,
    user: User,
    *,
    owner: str,
    repo: str,
    ref: str,
    path: str,
    strategy: RankingStrategy,
    target_type: Literal["file", "directory", "pull_request"] = "file",
    pr_number: int | None = None,
) -> WhoToAskResponse:
    token = await connector_service.get_required_access_token(db, user.id, "github")

    if target_type == "file":
        blame_ranges = await code_context_service.get_blame(token, owner, repo, ref, path)
        files_total = files_analyzed = 1
        files_skipped = 0
    else:
        if target_type == "pull_request":
            if pr_number is None:
                raise ValueError("pr_number is required when target_type is 'pull_request'")
            multi_file_blame = await code_context_service.get_blame_for_pull_request(
                token, owner, repo, ref, pr_number
            )
        else:
            multi_file_blame = await code_context_service.get_blame_for_directory(
                token, owner, repo, ref, path
            )
        # Flatten, then dedupe by commit sha across every file — a commit
        # touching 3 files (in the directory, or in the PR) is still one
        # touch, not three.
        blame_ranges = [r for file_blame in multi_file_blame.files for r in file_blame.ranges]
        files_total = multi_file_blame.files_total
        files_analyzed = multi_file_blame.files_analyzed
        files_skipped = multi_file_blame.files_skipped

    commits = _distinct_commits(blame_ranges)

    touches: list[Touch] = []
    commits_by_author: dict[str, list[CommitSummary]] = defaultdict(list)
    # Raw BlameRanges too, not just the display-oriented CommitSummary —
    # ticket-key extraction needs the full commit message plus associated
    # PR title/body, neither of which CommitSummary carries.
    blames_by_author: dict[str, list[BlameRange]] = defaultdict(list)
    for commit in commits:
        author = commit.author_login or commit.author_name
        if author is None:
            continue  # no identifiable author for this commit — nothing to rank
        touches.append(Touch(author=author, occurred_at=commit.committed_at))
        commits_by_author[author].append(
            CommitSummary(
                sha=commit.commit_sha,
                short_sha=commit.commit_sha[:7],
                message=commit.commit_message.split("\n")[0],
                committed_at=commit.committed_at,
                url=commit.commit_url,
            )
        )
        blames_by_author[author].append(commit)

    # Reviewers become additional touches, via their commentary on the
    # PRs associated with these commits — so someone who reviewed but
    # never committed still shows up in rankings (ADR 0016; `Touch` was
    # already generic enough for this — see its own docstring). One
    # lookup per *distinct PR* referenced by a blamed commit, not per
    # commit or per person — the same cost-bounding discipline as ADR
    # 0012's per-person Jira/Slack lookup.
    pr_titles_by_number = {
        c.pull_request.number: c.pull_request.title for c in commits if c.pull_request
    }
    reviews_by_author: dict[str, list[ReviewSummary]] = defaultdict(list)
    for pr_number in pr_titles_by_number:
        review_items = await correlation_service.find_review_comments_for_pr(
            db, user.id, owner, repo, pr_number
        )
        for r in review_items:
            if r.author is None:
                continue
            touches.append(Touch(author=r.author, occurred_at=r.occurred_at))
            reviews_by_author[r.author].append(
                ReviewSummary(
                    pr_number=pr_number,
                    pr_title=pr_titles_by_number[pr_number],
                    excerpt=r.excerpt,
                    url=r.url,
                    occurred_at=r.occurred_at,
                    state=r.state,
                )
            )

    ranked: list[RankedPerson] = (
        rank_by_recency(touches, now=datetime.now(UTC))
        if strategy == "recency"
        else rank_by_frequency(touches)
    )

    # Fetched once, not once per person — the credential doesn't change
    # mid-request.
    jira_site_url = await correlation_service.get_jira_site_url(db, user.id)

    people = []
    for p in ranked:
        ticket_key = _extract_ticket_key_from_recent_commits(blames_by_author[p.author])
        ticket_url = (
            correlation_service.build_jira_ticket_url(jira_site_url, ticket_key)
            if ticket_key
            else None
        )
        related_slack_msgs = await correlation_service.find_related(
            db, user.id, ticket_key, sources=["slack"]
        )
        similar_issue_msgs = (
            await correlation_service.find_similar_jira_issues(db, user.id, ticket_key)
            if ticket_key
            else []
        )

        people.append(
            PersonScore(
                author=p.author,
                score=p.score,
                touch_count=p.touch_count,
                last_touch_at=p.last_touch_at,
                commits=sorted(
                    commits_by_author[p.author], key=lambda c: c.committed_at, reverse=True
                ),
                reviews=sorted(
                    reviews_by_author[p.author], key=lambda r: r.occurred_at, reverse=True
                ),
                jira_ticket_key=ticket_key,
                jira_ticket_url=ticket_url,
                related_slack=[RelatedItem(**vars(m)) for m in related_slack_msgs],
                similar_issues=[RelatedItem(**vars(m)) for m in similar_issue_msgs],
            )
        )

    return WhoToAskResponse(
        people=people,
        strategy_used=strategy,
        files_total=files_total,
        files_analyzed=files_analyzed,
        files_skipped=files_skipped,
    )
