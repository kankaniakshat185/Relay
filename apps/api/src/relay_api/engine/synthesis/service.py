"""BYOK-or-free-tier-OpenAI answer synthesis (ADR 0008) — the orchestration
shared by every feature that wants "ask an LLM to answer/summarize over
some retrieved items," not just Context Search. Originally built inline in
`features/context_search/service.py`; moved here once Weekly Digest needed
the exact same logic — ADR 0005's rule ("if a feature ever needs another
feature's logic, that's a signal the shared logic belongs in `engine/`")
firing on a real case (see the ADR documenting this extraction).

Retrieval and prompt-building stay with each feature — a "candidate block"
and system prompt are feature-specific (Context Search answers a question;
Weekly Digest summarizes a time window). What's shared is everything after
that: resolving BYOK-vs-free-tier, calling the right provider, and
normalizing `SynthesisError` into a reason the caller can hand back to the
frontend without a 500.
"""

from dataclasses import dataclass, field

from relay_api.auth.models import User
from relay_api.core.config import get_settings
from relay_api.core.rate_limit import check_and_increment_daily
from relay_api.engine.ingestion.models import IngestedItem
from relay_api.engine.synthesis.providers import SYNTHESIS_PROVIDERS, SynthesisError
from relay_api.engine.synthesis.schemas import ItemCitation, LlmProvider, LlmUnavailableReason

_EXCERPT_LENGTH = 200

_DEFAULT_MODEL_BY_PROVIDER = {
    "openai": lambda settings: settings.synthesis_model,
    "groq": lambda settings: settings.groq_synthesis_model,
    "anthropic": lambda settings: settings.anthropic_synthesis_model,
    "gemini": lambda settings: settings.gemini_synthesis_model,
}


@dataclass
class SynthesisResult:
    used_llm: bool
    answer: str | None = None
    cited_indices: list[int] = field(default_factory=list)
    unavailable_reason: LlmUnavailableReason | None = None


def excerpt(body: str) -> str:
    text = " ".join(body.split())  # collapse whitespace/newlines to a clean single-line snippet
    if len(text) <= _EXCERPT_LENGTH:
        return text
    return text[:_EXCERPT_LENGTH].rsplit(" ", 1)[0] + "…"


def to_citation(item: IngestedItem) -> ItemCitation:
    return ItemCitation(
        source=item.source,
        source_type=item.source_type,
        title=item.title,
        url=item.url,
        author=item.author,
        occurred_at=item.occurred_at,
        excerpt=excerpt(item.body),
    )


async def synthesize_answer(
    user: User,
    system_prompt: str,
    user_prompt: str,
    *,
    provider: LlmProvider = "openai",
    byok_api_key: str | None = None,
) -> SynthesisResult:
    """Resolves BYOK-vs-free-tier-OpenAI, dispatches to the right provider,
    and normalizes the result. Callers still decide *whether* to call this
    at all (e.g. skipping it when there's nothing to synthesize over) and
    build their own response schema from the result — this only owns the
    "who pays, which provider, did it work" part."""
    settings = get_settings()
    api_key = byok_api_key
    model: str

    if api_key:
        model = _DEFAULT_MODEL_BY_PROVIDER[provider](settings)
    else:
        # No free tier outside OpenAI — Relay only ever pays for its own
        # OpenAI key, never someone else's provider bill.
        if provider != "openai":
            return SynthesisResult(used_llm=False, unavailable_reason="api_key_required")

        allowed = await check_and_increment_daily(
            f"free_llm:{user.id}", settings.free_llm_daily_limit
        )
        if not allowed:
            return SynthesisResult(used_llm=False, unavailable_reason="rate_limited")

        api_key = settings.openai_api_key
        model = settings.synthesis_model

    synthesize = SYNTHESIS_PROVIDERS[provider]
    try:
        answer, cited_indices = await synthesize(system_prompt, user_prompt, api_key, model)
    except SynthesisError as exc:
        # Single user-initiated call, not a batch job — no retry/backoff on
        # purpose (see providers.py). The caller just tries again.
        return SynthesisResult(used_llm=False, unavailable_reason=exc.reason)

    return SynthesisResult(used_llm=True, answer=answer, cited_indices=cited_indices)
