"""Given a file/module, who's worth asking about it? (plan.md §3). Blame
data comes from `engine.code_context` — same source Archaeology uses, on
purpose (ADR for this phase) — and the actual "who's most worth asking"
question is answered by `engine.ranking`'s two differential-tested
strategies, not decided here.

Scope cut, documented not silent: single-file only, same as Archaeology —
aggregating across every file in a directory ("module" level, per plan.md's
wording) is one blame call per file, left for a later pass.
"""

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors import service as connector_service
from relay_api.engine.code_context import service as code_context_service
from relay_api.engine.code_context.schemas import BlameRange
from relay_api.engine.ranking.schemas import RankedPerson, Touch
from relay_api.engine.ranking.strategies import rank_by_frequency, rank_by_recency
from relay_api.features.who_to_ask.schemas import (
    DirectoryEntry,
    PersonScore,
    RankingStrategy,
    RepoOption,
    WhoToAskResponse,
)

_SAMPLE_COMMITS_PER_PERSON = 2


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


def _distinct_commits(ranges: list[BlameRange]) -> list[BlameRange]:
    """One entry per commit sha — a commit that touched many lines in the
    blamed file is one touch by its author, not one per line range."""
    seen: dict[str, BlameRange] = {}
    for r in ranges:
        seen.setdefault(r.commit_sha, r)
    return list(seen.values())


async def rank(
    db: AsyncSession,
    user: User,
    *,
    owner: str,
    repo: str,
    ref: str,
    path: str,
    strategy: RankingStrategy,
) -> WhoToAskResponse:
    token = await connector_service.get_required_access_token(db, user.id, "github")
    blame_ranges = await code_context_service.get_blame(token, owner, repo, ref, path)
    commits = _distinct_commits(blame_ranges)

    touches: list[Touch] = []
    commit_urls_by_author: dict[str, list[str]] = defaultdict(list)
    for commit in commits:
        author = commit.author_login or commit.author_name
        if author is None:
            continue  # no identifiable author for this commit — nothing to rank
        touches.append(Touch(author=author, occurred_at=commit.committed_at))
        commit_urls_by_author[author].append(commit.commit_url)

    ranked: list[RankedPerson] = (
        rank_by_recency(touches, now=datetime.now(UTC))
        if strategy == "recency"
        else rank_by_frequency(touches)
    )

    people = [
        PersonScore(
            author=p.author,
            score=p.score,
            touch_count=p.touch_count,
            last_touch_at=p.last_touch_at,
            sample_commit_urls=commit_urls_by_author[p.author][:_SAMPLE_COMMITS_PER_PERSON],
        )
        for p in ranked
    ]

    return WhoToAskResponse(people=people, strategy_used=strategy)
