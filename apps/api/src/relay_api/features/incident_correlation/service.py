""" "What changed before this broke?" — a time window instead of a keyword
or a file, same retrieval shape as `features/weekly_digest`
(`engine.ingestion.service.get_items_since`), just bounded on both sides
around a past timestamp instead of open-ended to now. Narrative synthesis
reuses `engine.synthesis`, same BYOK-or-free-tier-OpenAI posture as every
other synthesizing feature (ADR 0008).

v2: if the request also names a file (`owner`/`repo`/`ref`/`file_path`),
this additionally calls `engine.timeline.build_timeline` — the exact
capability `features/archaeology` uses — and filters its result to the
incident window, so "what changed in this specific file right before the
incident" sits alongside "everything ingested in the window," not as a
separate query the user has to run themselves.
"""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors import service as connector_service
from relay_api.engine.ingestion.models import IngestedItem
from relay_api.engine.ingestion.service import get_items_since
from relay_api.engine.synthesis.schemas import LlmProvider
from relay_api.engine.synthesis.service import synthesize_answer, to_citation
from relay_api.engine.timeline import service as timeline_service
from relay_api.engine.timeline.schemas import TimelineEntry
from relay_api.features.incident_correlation.schemas import IncidentCorrelationResponse

_SYSTEM_PROMPT = (
    "You are Relay's incident-correlation assistant. You are given every GitHub, Slack, Jira, "
    "and personal-notes item that occurred in a time window around when a production incident "
    "was reported, each item with an index number. Write a short narrative — 2 to 4 sentences — "
    "identifying the most likely candidate change(s) that could explain the incident, and why. "
    "Prefer specific, recently-merged code changes (commits, PRs) over discussion. If nothing in "
    "the window looks like a plausible cause, say so plainly rather than forcing a guess. Return "
    "which candidate indices you actually drew the narrative from."
)


def _candidate_block(items: list[IngestedItem]) -> str:
    return "\n\n".join(
        f"[{i}] ({item.source}/{item.source_type}) {item.title}\n{item.body[:500]}"
        for i, item in enumerate(items)
    )


def _filter_to_window(
    entries: list[TimelineEntry], since: datetime, until: datetime
) -> list[TimelineEntry]:
    return [e for e in entries if since <= e.committed_at <= until]


async def correlate(
    db: AsyncSession,
    user: User,
    *,
    incident_at: datetime,
    window_before_hours: int = 48,
    window_after_hours: int = 2,
    owner: str | None = None,
    repo: str | None = None,
    ref: str | None = None,
    file_path: str | None = None,
    use_llm: bool = False,
    llm_provider: LlmProvider = "openai",
    byok_api_key: str | None = None,
) -> IncidentCorrelationResponse:
    since = incident_at - timedelta(hours=window_before_hours)
    until = incident_at + timedelta(hours=window_after_hours)

    items = await get_items_since(db, user.id, since=since, until=until)
    sources = [to_citation(item) for item in items]

    file_trace: list[TimelineEntry] = []
    if file_path is not None:
        assert owner is not None and repo is not None and ref is not None  # enforced by the schema
        token = await connector_service.get_required_access_token(db, user.id, "github")
        timeline_result = await timeline_service.build_timeline(
            db, user.id, access_token=token, owner=owner, repo=repo, ref=ref, path=file_path
        )
        file_trace = _filter_to_window(timeline_result.timeline, since, until)

    if not items or not use_llm:
        return IncidentCorrelationResponse(used_llm=False, sources=sources, file_trace=file_trace)

    user_prompt = (
        f"Incident reported at: {incident_at}.\n"
        f"Window: {window_before_hours}h before to {window_after_hours}h after.\n\n"
        f"Candidates:\n{_candidate_block(items)}"
    )
    result = await synthesize_answer(
        user, _SYSTEM_PROMPT, user_prompt, provider=llm_provider, byok_api_key=byok_api_key
    )

    if not result.used_llm:
        return IncidentCorrelationResponse(
            used_llm=False,
            llm_unavailable_reason=result.unavailable_reason,
            sources=sources,
            file_trace=file_trace,
        )

    valid_indices = [i for i in result.cited_indices if 0 <= i < len(items)]
    cited_items = [items[i] for i in valid_indices] or items

    return IncidentCorrelationResponse(
        used_llm=True,
        narrative=result.answer,
        sources=[to_citation(item) for item in cited_items],
        file_trace=file_trace,
    )
