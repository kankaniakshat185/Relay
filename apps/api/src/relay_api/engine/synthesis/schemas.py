from datetime import datetime
from typing import Literal

from pydantic import BaseModel

LlmProvider = Literal["openai", "groq", "anthropic", "gemini"]

LlmUnavailableReason = Literal[
    "rate_limited", "api_key_required", "invalid_api_key", "provider_error"
]


class ItemCitation(BaseModel):
    """An `IngestedItem` presented as a citation — generic to any feature
    that retrieves items and shows them back to the user (Context Search,
    Weekly Digest, ...), not specific to how any one feature retrieved
    them. Field names are unchanged from when this lived in
    `context_search/schemas.py` as `SourceCitation`, so the JSON wire shape
    callers already depend on doesn't change."""

    source: str
    source_type: str
    title: str
    url: str
    author: str | None
    occurred_at: datetime
    excerpt: str
