"""Retrieval (via `engine/indexing`) always runs and always works. Answer
synthesis is a separate, optional step — off by default, BYOK-across-four-
providers-or-rate-limited-OpenAI-free-tier when on (ADR 0008), delegated
to `engine.synthesis.service.synthesize_answer` (see the ADR documenting
that extraction) — the BYOK-vs-free-tier/provider-dispatch/error-handling
logic isn't specific to Context Search, only the prompt and the query are.

Every provider returns structured JSON (`answer` + which candidate indices
it actually drew from), not free-form prose we scrape for citations — so
the `sources` the frontend renders are real retrieved items with real
URLs, not the model's own citation formatting.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.engine.indexing.service import search as engine_search
from relay_api.engine.ingestion.models import IngestedItem
from relay_api.engine.synthesis.service import synthesize_answer, to_citation
from relay_api.features.context_search.schemas import ContextSearchResponse, LlmProvider

_SYSTEM_PROMPT = (
    "You are Relay's context search assistant. You are given a user's question and a list of "
    "candidate items retrieved from their GitHub, Slack, and Jira activity, each with an index "
    "number. Answer the question using only these items — do not use outside knowledge. Return "
    "which candidate indices you actually drew your answer from. If none of the candidates answer "
    "the question, say so plainly in the answer and return an empty list of indices."
)


def _candidate_block(items: list[IngestedItem]) -> str:
    return "\n\n".join(
        f"[{i}] ({item.source}/{item.source_type}) {item.title}\n{item.body[:500]}"
        for i, item in enumerate(items)
    )


async def search(
    db: AsyncSession,
    user: User,
    query: str,
    *,
    use_llm: bool = False,
    llm_provider: LlmProvider = "openai",
    byok_api_key: str | None = None,
    limit: int = 8,
) -> ContextSearchResponse:
    items = await engine_search(db, user.id, query, limit=limit)
    sources = [to_citation(item) for item in items]

    if not items or not use_llm:
        return ContextSearchResponse(used_llm=False, sources=sources)

    user_prompt = f"Question: {query}\n\nCandidates:\n{_candidate_block(items)}"
    result = await synthesize_answer(
        user, _SYSTEM_PROMPT, user_prompt, provider=llm_provider, byok_api_key=byok_api_key
    )

    if not result.used_llm:
        return ContextSearchResponse(
            used_llm=False, llm_unavailable_reason=result.unavailable_reason, sources=sources
        )

    valid_indices = [i for i in result.cited_indices if 0 <= i < len(items)]
    cited_items = [items[i] for i in valid_indices] or items

    return ContextSearchResponse(
        used_llm=True,
        answer=result.answer,
        sources=[to_citation(item) for item in cited_items],
    )
