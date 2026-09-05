"""Flags pull requests with real correlated discussion (Slack/Jira) but
no correlated decision doc — "decision debt": a change that clearly
involved back-and-forth deliberation, with no written record of why it
was made the way it was. Reuses `engine.correlation`'s exact
ticket-key-then-semantic-search pipeline that already powers Archaeology
and Who Should I Ask — scoped to decision-doc ingestion (ADR 0027, see
`connectors/github/ingest.py`) instead of a new correlation mechanism.

Also flags whether a PR's author has any recent commit activity across
ALL of this user's connected repos — a flagged PR whose author looks
gone is a stronger signal than one whose author is still around and
could just be asked directly.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.engine.correlation.service import extract_ticket_key, find_related
from relay_api.engine.ingestion.models import IngestedItem
from relay_api.features.decision_debt.schemas import (
    DecisionDebtResponse,
    FlaggedPullRequest,
    RelatedItem,
)

_DISCUSSION_LIMIT = 10
"""Capped, not exhaustive — `flagged[].discussion` is evidence for why a
PR got flagged, not a full transcript. Same "show enough to judge, not
everything" posture as `find_related`'s own default limit elsewhere."""


async def _count_decision_docs(db: AsyncSession, user_id: uuid.UUID, repo_full_name: str) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(IngestedItem)
        .where(
            IngestedItem.user_id == user_id,
            IngestedItem.source == "github",
            IngestedItem.source_type == "decision_doc",
            IngestedItem.extra["repo"].astext == repo_full_name,
        )
    )
    return count or 0


async def _is_author_inactive(
    db: AsyncSession, user_id: uuid.UUID, author: str | None, inactive_after_days: int
) -> bool:
    """`False` (not an error, not "unknown") whenever there isn't enough
    signal to claim inactivity — no author at all, or no commit history
    for them anywhere this user has connected. Only a genuinely stale
    `MAX(occurred_at)` earns a `True`."""
    if author is None:
        return False

    latest = await db.scalar(
        select(func.max(IngestedItem.occurred_at)).where(
            IngestedItem.user_id == user_id,
            IngestedItem.source == "github",
            IngestedItem.source_type == "commit",
            IngestedItem.author == author,
        )
    )
    if latest is None:
        return False

    return (datetime.now(UTC) - latest) > timedelta(days=inactive_after_days)


async def scan(
    db: AsyncSession,
    user: User,
    *,
    owner: str,
    repo: str,
    min_discussion_items: int = 2,
    inactive_after_days: int = 180,
) -> DecisionDebtResponse:
    repo_full_name = f"{owner}/{repo}"

    result = await db.execute(
        select(IngestedItem).where(
            IngestedItem.user_id == user.id,
            IngestedItem.source == "github",
            IngestedItem.source_type == "pull_request",
            IngestedItem.extra["repo"].astext == repo_full_name,
        )
    )
    prs = list(result.scalars().all())

    decision_docs_found = await _count_decision_docs(db, user.id, repo_full_name)

    flagged: list[FlaggedPullRequest] = []
    for pr in prs:
        ticket_key = extract_ticket_key(pr.title, pr.body)
        query = ticket_key or pr.title

        discussion = await find_related(
            db, user.id, query, sources=["slack", "jira"], limit=_DISCUSSION_LIMIT
        )
        if len(discussion) < min_discussion_items:
            continue

        documented = await find_related(
            db, user.id, query, sources=["github"], source_types=["decision_doc"], limit=1
        )
        if documented:
            continue

        author_inactive = await _is_author_inactive(db, user.id, pr.author, inactive_after_days)

        flagged.append(
            FlaggedPullRequest(
                number=pr.extra["number"],
                title=pr.title,
                url=pr.url,
                author=pr.author,
                author_inactive=author_inactive,
                discussion=[RelatedItem(**vars(item)) for item in discussion],
            )
        )

    return DecisionDebtResponse(
        flagged=flagged, prs_scanned=len(prs), decision_docs_found=decision_docs_found
    )
