from pydantic import BaseModel

from relay_api.engine.synthesis.schemas import ItemCitation, LlmProvider, LlmUnavailableReason

__all__ = [
    "ContextSearchRequest",
    "ContextSearchResponse",
    "LlmProvider",
    "LlmUnavailableReason",
]


class ContextSearchRequest(BaseModel):
    query: str
    use_llm: bool = False
    """Off by default (ADR 0008) — raw retrieval always works with zero LLM
    cost. Set true to additionally synthesize an answer."""
    llm_provider: LlmProvider = "openai"
    api_key: str | None = None
    """BYOK — used transiently for this one request only, never persisted.
    Ignored when use_llm is false. When empty, falls back to the server's
    shared OpenAI key, subject to a per-user daily rate limit — the free
    tier is OpenAI-only regardless of llm_provider (see core/rate_limit.py)."""


class ContextSearchResponse(BaseModel):
    used_llm: bool
    """Whether an answer was actually synthesized. Sources are always
    populated regardless of this."""
    llm_unavailable_reason: LlmUnavailableReason | None = None
    answer: str | None = None
    sources: list[ItemCitation]
