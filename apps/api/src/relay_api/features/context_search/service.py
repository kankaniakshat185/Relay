"""Retrieval (via `engine/indexing`) + synthesis (OpenAI, ADR 0007).

The model returns structured JSON (`answer` + which candidate indices it
actually drew from), not free-form prose we scrape for citations — so the
`sources` the frontend renders are real retrieved items with real URLs,
not the model's own citation formatting.
"""

import json

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONSchema
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.core.config import get_settings
from relay_api.engine.indexing.service import search as engine_search
from relay_api.engine.ingestion.models import IngestedItem
from relay_api.features.context_search.schemas import ContextSearchResponse, SourceCitation

_SYSTEM_PROMPT = (
    "You are Relay's context search assistant. You are given a user's question and a list of "
    "candidate items retrieved from their GitHub, Slack, and Jira activity, each with an index "
    "number. Answer the question using only these items — do not use outside knowledge. Return "
    "which candidate indices you actually drew your answer from. If none of the candidates answer "
    "the question, say so plainly in the answer and return an empty list of indices."
)

_RESPONSE_FORMAT: ResponseFormatJSONSchema = {
    "type": "json_schema",
    "json_schema": {
        "name": "context_search_answer",
        "schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "cited_indices": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["answer", "cited_indices"],
            "additionalProperties": False,
        },
    },
}

_NO_DATA_ANSWER = "No connected data yet to search — connect GitHub, Slack, or Jira first."


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
    )


async def search(
    db: AsyncSession, user: User, query: str, *, limit: int = 8
) -> ContextSearchResponse:
    items = await engine_search(db, user.id, query, limit=limit)
    if not items:
        return ContextSearchResponse(answer=_NO_DATA_ANSWER, sources=[])

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {query}\n\nCandidates:\n{_candidate_block(items)}"},
    ]
    response = await client.chat.completions.create(
        model=settings.synthesis_model,
        messages=messages,
        response_format=_RESPONSE_FORMAT,
    )
    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)

    cited_indices = [i for i in parsed.get("cited_indices", []) if 0 <= i < len(items)]
    cited_items = [items[i] for i in cited_indices] or items  # fall back to showing all retrieved

    return ContextSearchResponse(
        answer=parsed.get("answer", ""),
        sources=[_to_citation(item) for item in cited_items],
    )
