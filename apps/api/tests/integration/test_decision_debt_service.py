"""`features/decision_debt.service.scan` against a real Postgres — uses
exact ticket-key correlation throughout (same technique as
`test_correlation_exact_match.py`) so results are deterministic without
needing to craft embeddings that land on either side of
`_MIN_RELEVANCE_SCORE`. Items are deliberately never run through
`indexing_service.index_items` — the exact-ticket-key path
(`_find_exact_ticket_key_matches`) doesn't require `embedding IS NOT
NULL`, so this exercises exactly the path real, freshly-ingested (not
yet indexed) items would take too.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.engine.indexing import service as indexing_service
from relay_api.engine.ingestion import service as ingestion_service
from relay_api.engine.ingestion.schemas import NormalizedItem
from relay_api.features.decision_debt import service as decision_debt_service

_REPO = "acme/widgets"


def _pr(number: int, ticket_key: str, author: str | None = "octocat") -> NormalizedItem:
    return NormalizedItem(
        source="github",
        source_type="pull_request",
        external_id=f"pr-{number}",
        title=f"{ticket_key}: fix retry logic",
        body="",
        url=f"https://github.com/acme/widgets/pull/{number}",
        author=author,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={"repo": _REPO, "state": "open", "number": number},
    )


def _slack_message(external_id: str, ticket_key: str) -> NormalizedItem:
    return NormalizedItem(
        source="slack",
        source_type="message",
        external_id=external_id,
        title=f"discussing {ticket_key}",
        body=f"a lot of back and forth about {ticket_key} here",
        url=f"https://acme.slack.com/archives/C1/{external_id}",
        author="alice",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _decision_doc(external_id: str, ticket_key: str) -> NormalizedItem:
    return NormalizedItem(
        source="github",
        source_type="decision_doc",
        external_id=external_id,
        title=f"ADR: {ticket_key}",
        body=f"Documents the decision behind {ticket_key}.",
        url=f"https://github.com/acme/widgets/blob/HEAD/docs/adr/{external_id}.md",
        author="octocat",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={"repo": _REPO, "path": f"docs/adr/{external_id}.md"},
    )


def _commit(external_id: str, author: str, occurred_at: datetime) -> NormalizedItem:
    return NormalizedItem(
        source="github",
        source_type="commit",
        external_id=external_id,
        title="a commit",
        body="a commit",
        url=f"https://github.com/acme/widgets/commit/{external_id}",
        author=author,
        occurred_at=occurred_at,
        extra={"repo": _REPO, "sha": external_id},
    )


async def _fake_embed(texts: list[str]) -> list[list[float]]:
    # Never actually reached by a real assertion here — every case below
    # is decided by the exact-ticket-key path, not the semantic one — but
    # `find_related` still embeds the query text on its way there, so
    # this only exists to keep that from making a real API call.
    from relay_api.engine.ingestion.models import EMBEDDING_DIMENSIONS

    return [[0.1] * EMBEDDING_DIMENSIONS for _ in texts]


async def test_flags_a_pr_with_real_discussion_and_no_decision_doc(
    db: AsyncSession, test_user: User
) -> None:
    pr = _pr(1, "REL-42")
    messages = [_slack_message(f"msg-{i}", "REL-42") for i in range(2)]
    await ingestion_service.upsert_items(db, test_user.id, [pr, *messages])

    with patch.object(indexing_service, "embed_texts", new=_fake_embed):
        result = await decision_debt_service.scan(
            db, test_user, owner="acme", repo="widgets", min_discussion_items=2
        )

    assert result.prs_scanned == 1
    assert result.decision_docs_found == 0
    assert [f.number for f in result.flagged] == [1]
    assert len(result.flagged[0].discussion) == 2


async def test_a_pr_with_a_correlated_decision_doc_is_not_flagged(
    db: AsyncSession, test_user: User
) -> None:
    pr = _pr(2, "REL-43")
    messages = [_slack_message(f"msg-doc-{i}", "REL-43") for i in range(2)]
    doc = _decision_doc("0001", "REL-43")
    await ingestion_service.upsert_items(db, test_user.id, [pr, *messages, doc])

    with patch.object(indexing_service, "embed_texts", new=_fake_embed):
        result = await decision_debt_service.scan(
            db, test_user, owner="acme", repo="widgets", min_discussion_items=2
        )

    assert result.decision_docs_found == 1
    assert result.flagged == []


async def test_a_pr_below_the_discussion_threshold_is_not_flagged(
    db: AsyncSession, test_user: User
) -> None:
    pr = _pr(3, "REL-44")
    # Only one message — below the default min_discussion_items=2.
    await ingestion_service.upsert_items(db, test_user.id, [pr, _slack_message("msg-1", "REL-44")])

    with patch.object(indexing_service, "embed_texts", new=_fake_embed):
        result = await decision_debt_service.scan(db, test_user, owner="acme", repo="widgets")

    assert result.prs_scanned == 1
    assert result.flagged == []


async def test_prs_are_scoped_to_the_requested_repo(db: AsyncSession, test_user: User) -> None:
    matching = _pr(4, "REL-45")
    other_repo_pr = NormalizedItem(
        source="github",
        source_type="pull_request",
        external_id="pr-other-repo",
        title="REL-46: unrelated",
        body="",
        url="https://github.com/acme/other-repo/pull/1",
        author="octocat",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={"repo": "acme/other-repo", "state": "open", "number": 1},
    )
    await ingestion_service.upsert_items(db, test_user.id, [matching, other_repo_pr])

    with patch.object(indexing_service, "embed_texts", new=_fake_embed):
        result = await decision_debt_service.scan(db, test_user, owner="acme", repo="widgets")

    assert result.prs_scanned == 1


async def test_author_inactive_true_when_last_commit_is_stale(
    db: AsyncSession, test_user: User
) -> None:
    pr = _pr(5, "REL-47", author="dave")
    messages = [_slack_message(f"msg-inactive-{i}", "REL-47") for i in range(2)]
    stale_commit = _commit("stale-sha", "dave", datetime.now(UTC) - timedelta(days=400))
    await ingestion_service.upsert_items(db, test_user.id, [pr, *messages, stale_commit])

    with patch.object(indexing_service, "embed_texts", new=_fake_embed):
        result = await decision_debt_service.scan(
            db, test_user, owner="acme", repo="widgets", inactive_after_days=180
        )

    assert len(result.flagged) == 1
    assert result.flagged[0].author_inactive is True


async def test_author_inactive_false_when_last_commit_is_recent(
    db: AsyncSession, test_user: User
) -> None:
    pr = _pr(6, "REL-48", author="carol")
    messages = [_slack_message(f"msg-active-{i}", "REL-48") for i in range(2)]
    recent_commit = _commit("recent-sha", "carol", datetime.now(UTC) - timedelta(days=5))
    await ingestion_service.upsert_items(db, test_user.id, [pr, *messages, recent_commit])

    with patch.object(indexing_service, "embed_texts", new=_fake_embed):
        result = await decision_debt_service.scan(
            db, test_user, owner="acme", repo="widgets", inactive_after_days=180
        )

    assert len(result.flagged) == 1
    assert result.flagged[0].author_inactive is False


async def test_author_inactive_false_with_no_commit_history_at_all(
    db: AsyncSession, test_user: User
) -> None:
    # "erin" authored this PR but never shows up as a commit author
    # anywhere this user has connected — insufficient signal to claim
    # inactivity, not proof of activity, so this must stay False.
    pr = _pr(7, "REL-49", author="erin")
    messages = [_slack_message(f"msg-unknown-{i}", "REL-49") for i in range(2)]
    await ingestion_service.upsert_items(db, test_user.id, [pr, *messages])

    with patch.object(indexing_service, "embed_texts", new=_fake_embed):
        result = await decision_debt_service.scan(db, test_user, owner="acme", repo="widgets")

    assert len(result.flagged) == 1
    assert result.flagged[0].author_inactive is False
