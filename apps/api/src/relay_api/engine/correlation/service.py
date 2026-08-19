"""Cross-source correlation shared by `features/archaeology` and
`features/who_to_ask` — extracting a Jira ticket key from GitHub text and
finding related Slack discussion for it. Originally lived entirely inside
`features/archaeology/service.py`; moved here once `features/who_to_ask`
needed the exact same logic (ADR 0005: shared feature logic belongs in
engine, not duplicated — see ADR 0012).

Also finds a PR's review commentary (`find_review_comments_for_pr`, ADR
0016) — a direct DB filter, not a search, but it belongs here rather than
a new module for the same reason `find_similar_jira_issues` does: still
DB-only, no live external calls, same "what's related to this" job.

Deliberately still no ranking/scoring here, same discipline as the rest
of `engine/` — this module answers "what's related," not "what matters
most."
"""

import re
import uuid
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.connectors import service as connector_service
from relay_api.engine.correlation.schemas import RelatedItem, ReviewItem
from relay_api.engine.indexing.service import search as engine_search
from relay_api.engine.ingestion.models import IngestedItem

# Matches the common Jira key shape (PROJECT-123). Also matches some
# non-ticket strings that happen to look the same (e.g. "UTF-8") — a
# known, accepted false-positive rate rather than a fully-solved NLP
# problem; see the phase 2 retro.
_TICKET_KEY_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")

_EXCERPT_LENGTH = 200
_DEFAULT_RELATED_LIMIT = 3

_MIN_RELEVANCE_SCORE = 0.4
"""Below this combined score (`engine.indexing.service.search`'s
`0.4*keyword_rank + 0.6*vector_similarity`), a candidate is discarded
rather than shown as "related" — found live: with a small ingested
corpus, `search()`'s `ORDER BY score LIMIT N` always returns N results
regardless of relevance, so "related Slack discussion" for a commit with
zero actual Slack activity was showing 3 unrelated messages just because
3 was all that existed. Empirically checked against real ingested data,
not guessed: genuine matches (an exact ticket-key hit) scored 0.58-0.66;
the noise floor from vector similarity alone on short, topically
unrelated business text (`keyword_rank == 0`, `vector_similarity` alone
carrying the score) topped out at 0.38 even at its highest. 0.4 sits in
the gap with margin on both sides — not a universal constant, revisit if
real usage shows either false negatives (a real match scoring low) or
this still letting weak matches through."""


def extract_ticket_key(*texts: str) -> str | None:
    """Checks each text in order, returns the first Jira-shaped key
    found — callers pass their own fallback chain (e.g. commit message,
    then PR title, then PR body)."""
    for text in texts:
        match = _TICKET_KEY_PATTERN.search(text)
        if match:
            return match.group(0)
    return None


async def get_jira_site_url(db: AsyncSession, user_id: uuid.UUID) -> str | None:
    """One credential lookup — callers fetch this once per request and
    reuse it, rather than re-querying per commit/person (the bug this
    extraction fixed in Archaeology, which used to do exactly that)."""
    credential = await connector_service.get_credential(db, user_id, "jira")
    if credential is None:
        return None
    return credential.external_account_label.rstrip("/")


def build_jira_ticket_url(site_url: str | None, ticket_key: str) -> str | None:
    if site_url is None:
        return None
    return f"{site_url}/browse/{ticket_key}"


def _to_related_item(item: IngestedItem) -> RelatedItem:
    # `IngestedItem.source` is a plain str column (any connector could
    # write it); narrowing to the two sources this module's callers ever
    # pass into `sources=` is safe here, not a general assumption.
    source = cast(Literal["slack", "jira"], item.source)
    return RelatedItem(
        source=source,
        title=item.title,
        url=item.url,
        excerpt=" ".join(item.body.split())[:_EXCERPT_LENGTH],
        occurred_at=item.occurred_at,
    )


async def find_related(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str | None,
    *,
    sources: list[str],
    limit: int = _DEFAULT_RELATED_LIMIT,
) -> list[RelatedItem]:
    """Generic "find items related to this text" — Archaeology/Who Should
    I Ask use this scoped to `sources=["slack"]` for discussion related to
    a ticket, and `find_similar_jira_issues` below builds on it scoped to
    `["jira"]` for similar past issues. One retrieval path (Phase 1's
    hybrid search), two callers, not two implementations."""
    if not query:
        return []
    items = await engine_search(
        db, user_id, query, sources=sources, limit=limit, min_score=_MIN_RELEVANCE_SCORE
    )
    return [_to_related_item(item) for item in items]


async def find_similar_jira_issues(
    db: AsyncSession, user_id: uuid.UUID, ticket_key: str, *, limit: int = _DEFAULT_RELATED_LIMIT
) -> list[RelatedItem]:
    """Given a ticket key already found in a commit/PR, finds other Jira
    issues this user has ingested that are semantically similar to it —
    using the ticket's own title+body as the search query, not the bare
    key (a key match would just find *mentions* of this ticket, not
    issues actually like it).

    Returns `[]`, not an error, if the ticket itself was never ingested
    (a different Jira site than the one connected, or simply not indexed
    yet) — there's nothing to compare against, which isn't a failure."""
    ticket = await db.scalar(
        select(IngestedItem).where(
            IngestedItem.user_id == user_id,
            IngestedItem.source == "jira",
            IngestedItem.extra["key"].astext == ticket_key,
        )
    )
    if ticket is None:
        return []

    query = f"{ticket.title}\n\n{ticket.body}"
    # Fetch one extra and drop the ticket's own row rather than teaching
    # the shared `search()` about exclusion — this is the only caller
    # that needs it.
    candidates = await find_related(db, user_id, query, sources=["jira"], limit=limit + 1)
    return [c for c in candidates if c.url != ticket.url][:limit]


def _to_review_item(item: IngestedItem) -> ReviewItem:
    return ReviewItem(
        author=item.author,
        excerpt=" ".join(item.body.split())[:_EXCERPT_LENGTH],
        url=item.url,
        occurred_at=item.occurred_at,
        state=item.extra.get("state"),
    )


async def find_review_comments_for_pr(
    db: AsyncSession, user_id: uuid.UUID, owner: str, repo: str, pr_number: int
) -> list[ReviewItem]:
    """Review commentary (top-level verdicts + inline comments) on one
    PR, oldest first. A direct `extra->>'pr_number'` filter, not a
    semantic search — unlike the Jira/Slack correlation above, a review
    genuinely belongs to exactly one PR, a real FK-like relationship, not
    something to guess at via similarity."""
    result = await db.execute(
        select(IngestedItem)
        .where(
            IngestedItem.user_id == user_id,
            IngestedItem.source == "github",
            IngestedItem.source_type == "review_comment",
            IngestedItem.extra["repo"].astext == f"{owner}/{repo}",
            IngestedItem.extra["pr_number"].astext == str(pr_number),
        )
        .order_by(IngestedItem.occurred_at.asc())
    )
    return [_to_review_item(item) for item in result.scalars().all()]


def has_unresolved_concerns(reviews: list[ReviewItem]) -> bool:
    """Heuristic, not ground truth — same discipline as ticket-key
    extraction's known false-positive rate. True when the most recent
    top-level review *verdict* (inline comments, `state is None`, don't
    count) is CHANGES_REQUESTED with no later APPROVED from anyone. A
    real PR can be far more nuanced than this (multiple reviewers,
    re-requested review, comments resolved out of band) — this only
    answers "does the review history, read literally, still end on a
    rejection.\""""
    verdicts = sorted(
        (r for r in reviews if r.state in ("APPROVED", "CHANGES_REQUESTED")),
        key=lambda r: r.occurred_at,
    )
    if not verdicts:
        return False
    return verdicts[-1].state == "CHANGES_REQUESTED"
