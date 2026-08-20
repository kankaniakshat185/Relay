from pydantic import BaseModel, Field

from relay_api.engine.synthesis.schemas import ItemCitation, LlmProvider, LlmUnavailableReason


class WeeklyDigestRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=30)
    """The window to summarize. Bounded, not open-ended — `get_items_since`
    is a live, on-demand read (no new ingestion job), so this stays a
    small enough window to answer in one request."""
    use_llm: bool = False
    """Off by default, same principle as Context Search (ADR 0008) — raw
    retrieval (grouped, time-ordered sources) always works with zero LLM
    cost. Set true to additionally synthesize a written digest."""
    llm_provider: LlmProvider = "openai"
    api_key: str | None = None
    """BYOK — used transiently for this one request only, never persisted.
    Ignored when use_llm is false."""


class WeeklyDigestResponse(BaseModel):
    used_llm: bool
    """Whether a digest was actually synthesized. Sources are always
    populated regardless of this."""
    llm_unavailable_reason: LlmUnavailableReason | None = None
    digest: str | None = None
    sources: list[ItemCitation]
