from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from relay_api.engine.synthesis.schemas import ItemCitation, LlmProvider, LlmUnavailableReason
from relay_api.engine.timeline.schemas import TimelineEntry


class IncidentCorrelationRequest(BaseModel):
    incident_at: datetime
    """When the incident was noticed or reported — the anchor the window
    is built around, not necessarily when the root cause actually landed."""
    window_before_hours: int = Field(default=48, ge=1, le=24 * 14)
    """How far back to look for candidate changes. 48h by default — wide
    enough to catch a change that took a day to manifest, narrow enough
    that a real query still returns a small, skimmable set."""
    window_after_hours: int = Field(default=2, ge=0, le=24 * 7)
    """A small forward window too, not just backward — "did a fix already
    land" is as real a question as "what caused this." Small default
    since a genuine root cause is virtually always before the incident,
    not after."""

    owner: str | None = None
    repo: str | None = None
    ref: str | None = None
    file_path: str | None = None
    """v2: if the incident report names a specific file/service, this
    also traces that file's own commit history (`engine.timeline`,
    the same capability `features/archaeology` uses) filtered to the
    incident window — not just what's already been ingested, but the
    live, authoritative blame history for that one file. Optional:
    v1 (everything ingested in the window) works with none of these set."""

    use_llm: bool = False
    """Off by default, same posture as Context Search (ADR 0008) and
    Weekly Digest — raw retrieval (grouped, time-ordered candidates)
    always works with zero LLM cost."""
    llm_provider: LlmProvider = "openai"
    api_key: str | None = None
    """BYOK — used transiently for this one request only, never persisted."""

    @field_validator("incident_at")
    @classmethod
    def _assume_utc_if_no_timezone_given(cls, value: datetime) -> datetime:
        # Every timestamp elsewhere in this app is UTC (`datetime.now(UTC)`,
        # `IngestedItem.occurred_at`) — comparing a naive `incident_at`
        # against those raises `TypeError` deep in `service.correlate`,
        # not a clean validation error. A browser's `<input
        # type="datetime-local">` has no timezone at all, so assuming UTC
        # here (rather than rejecting) is what makes that input usable
        # without the frontend doing its own conversion.
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @model_validator(mode="after")
    def _file_trace_requires_owner_repo_and_ref(self) -> "IncidentCorrelationRequest":
        # A clean 422 via Pydantic's own validation, not a raw 500 out of
        # `service.correlate`'s own defensive check — same "reject bad
        # input at the boundary" discipline as `who_to_ask`'s pr_number
        # validator.
        if self.file_path is not None and not (self.owner and self.repo and self.ref):
            raise ValueError("owner, repo, and ref are all required when file_path is given")
        return self


class IncidentCorrelationResponse(BaseModel):
    used_llm: bool
    """Whether a narrative was actually synthesized. `sources` (and
    `file_trace`, if requested) are always populated regardless."""
    llm_unavailable_reason: LlmUnavailableReason | None = None
    narrative: str | None = None
    sources: list[ItemCitation]
    """Everything ingested in the window, most recent first — the v1
    result, always present."""
    file_trace: list[TimelineEntry] = []
    """v2: `file_path`'s own commit history, filtered to the incident
    window — empty whenever `file_path` wasn't given, not just omitted,
    so the frontend never needs to distinguish "not requested" from
    "requested, nothing found" via a missing key."""
