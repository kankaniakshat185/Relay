"""Retrieval (via `engine.ingestion.service.get_items_since`) always runs
and always works. Digest synthesis is a separate, optional step — off by
default, same BYOK-or-free-tier-OpenAI posture as Context Search (ADR
0008), via `engine.synthesis.service.synthesize_answer`. See the ADR
documenting the `engine/synthesis` extraction for why this feature and
Context Search share that machinery instead of each having their own.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.engine.ingestion.models import IngestedItem
from relay_api.engine.ingestion.service import get_items_since
from relay_api.engine.synthesis.schemas import LlmProvider
from relay_api.engine.synthesis.service import synthesize_answer, to_citation
from relay_api.features.weekly_digest.schemas import WeeklyDigestResponse

_SYSTEM_PROMPT = (
    "You are Relay's weekly digest assistant. You are given everything a user's connected "
    "GitHub, Slack, Jira, and personal notes recorded in a recent time window, each item with an "
    "index number. Structure the digest as exactly three sections, in this order, each starting "
    "with its label alone on its own line, in all caps, with nothing else on that line:\n\n"
    "SHIPPED\n"
    "<a short paragraph on what actually shipped or landed>\n\n"
    "STILL IN MOTION\n"
    "<a short paragraph on what's still being actively discussed or in progress>\n\n"
    "UNRESOLVED\n"
    "<a short paragraph on what looks unresolved or blocked>\n\n"
    "Group related items together within a section (e.g. a PR, its review comments, and the "
    "Slack thread about it) rather than listing every item separately. If a section has nothing "
    'to report, write "Nothing notable." under that label rather than omitting the label — all '
    "three labels must always appear, in order. Return which candidate indices you actually drew "
    "the digest from. If the window is empty or nothing notable happened at all, say so under "
    "each label and return an empty list of indices."
)


def _candidate_block(items: list[IngestedItem]) -> str:
    return "\n\n".join(
        f"[{i}] ({item.source}/{item.source_type}) {item.title}\n{item.body[:500]}"
        for i, item in enumerate(items)
    )


async def build_digest(
    db: AsyncSession,
    user: User,
    *,
    days: int = 7,
    use_llm: bool = False,
    llm_provider: LlmProvider = "openai",
    byok_api_key: str | None = None,
) -> WeeklyDigestResponse:
    since = datetime.now(UTC) - timedelta(days=days)
    items = await get_items_since(db, user.id, since)
    sources = [to_citation(item) for item in items]

    if not items or not use_llm:
        return WeeklyDigestResponse(used_llm=False, sources=sources)

    user_prompt = f"Time window: the last {days} day(s).\n\nCandidates:\n{_candidate_block(items)}"
    result = await synthesize_answer(
        user, _SYSTEM_PROMPT, user_prompt, provider=llm_provider, byok_api_key=byok_api_key
    )

    if not result.used_llm:
        return WeeklyDigestResponse(
            used_llm=False, llm_unavailable_reason=result.unavailable_reason, sources=sources
        )

    valid_indices = [i for i in result.cited_indices if 0 <= i < len(items)]
    cited_items = [items[i] for i in valid_indices] or items

    return WeeklyDigestResponse(
        used_llm=True,
        digest=result.answer,
        sources=[to_citation(item) for item in cited_items],
    )
