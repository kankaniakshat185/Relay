"""Retrieval (via `engine/indexing`) always runs and always works. Answer
synthesis is a separate, optional step — off by default, BYOK-across-four-
providers-or-rate-limited-OpenAI-free-tier when on (ADR 0008).

Every provider returns structured JSON (`answer` + which candidate indices
it actually drew from), not free-form prose we scrape for citations — so
the `sources` the frontend renders are real retrieved items with real
URLs, not the model's own citation formatting. See `llm_providers.py` for
the per-provider SDK calls.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.core.config import get_settings
from relay_api.core.rate_limit import check_and_increment_daily
from relay_api.engine.indexing.service import search as engine_search
from relay_api.engine.ingestion.models import IngestedItem
from relay_api.features.context_search.llm_providers import SYNTHESIS_PROVIDERS, SynthesisError
from relay_api.features.context_search.schemas import (
    ContextSearchResponse,
    LlmProvider,
    SourceCitation,
)

_SYSTEM_PROMPT = (
    "You are Relay's context search assistant. You are given a user's question and a list of "
    "candidate items retrieved from their GitHub, Slack, and Jira activity, each with an index "
    "number. Answer the question using only these items — do not use outside knowledge. Return "
    "which candidate indices you actually drew your answer from. If none of the candidates answer "
    "the question, say so plainly in the answer and return an empty list of indices."
)

_EXCERPT_LENGTH = 200

_DEFAULT_MODEL_BY_PROVIDER = {
    "openai": lambda settings: settings.synthesis_model,
    "groq": lambda settings: settings.groq_synthesis_model,
    "anthropic": lambda settings: settings.anthropic_synthesis_model,
    "gemini": lambda settings: settings.gemini_synthesis_model,
}


def _excerpt(body: str) -> str:
    text = " ".join(body.split())  # collapse whitespace/newlines to a clean single-line snippet
    if len(text) <= _EXCERPT_LENGTH:
        return text
    return text[:_EXCERPT_LENGTH].rsplit(" ", 1)[0] + "…"


def _candidate_block(items: list[IngestedItem]) -> str:
    return "\n\n".join(
        f"[{i}] ({item.source}/{item.source_type}) {item.title}\n{item.body[:500]}"
        for i, item in enumerate(items)
    )


def _to_citation(item: IngestedItem) -> SourceCitation:
    return SourceCitation(
        source=item.source,
        source_type=item.source_type,
        title=item.title,
        url=item.url,
        author=item.author,
        occurred_at=item.occurred_at,
        excerpt=_excerpt(item.body),
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
    sources = [_to_citation(item) for item in items]

    if not items or not use_llm:
        return ContextSearchResponse(used_llm=False, sources=sources)

    settings = get_settings()
    api_key = byok_api_key
    provider = llm_provider
    model: str

    if api_key:
        model = _DEFAULT_MODEL_BY_PROVIDER[provider](settings)
    else:
        # No free tier outside OpenAI — Relay only ever pays for its own
        # OpenAI key, never someone else's provider bill.
        if provider != "openai":
            return ContextSearchResponse(
                used_llm=False, llm_unavailable_reason="api_key_required", sources=sources
            )

        allowed = await check_and_increment_daily(
            f"free_llm:{user.id}", settings.free_llm_daily_limit
        )
        if not allowed:
            return ContextSearchResponse(
                used_llm=False, llm_unavailable_reason="rate_limited", sources=sources
            )

        api_key = settings.openai_api_key
        model = settings.synthesis_model

    synthesize = SYNTHESIS_PROVIDERS[provider]
    user_prompt = f"Question: {query}\n\nCandidates:\n{_candidate_block(items)}"
    try:
        answer, cited_indices = await synthesize(_SYSTEM_PROMPT, user_prompt, api_key, model)
    except SynthesisError as exc:
        # Single user-initiated call, not a batch job — no retry/backoff on
        # purpose (see llm_providers.py). The user just searches again.
        return ContextSearchResponse(
            used_llm=False, llm_unavailable_reason=exc.reason, sources=sources
        )

    valid_indices = [i for i in cited_indices if 0 <= i < len(items)]
    cited_items = [items[i] for i in valid_indices] or items

    return ContextSearchResponse(
        used_llm=True,
        answer=answer,
        sources=[_to_citation(item) for item in cited_items],
    )
