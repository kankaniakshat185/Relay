from datetime import datetime

from pydantic import BaseModel


class ContextSearchRequest(BaseModel):
    query: str


class SourceCitation(BaseModel):
    source: str
    source_type: str
    title: str
    url: str
    author: str | None
    occurred_at: datetime


class ContextSearchResponse(BaseModel):
    answer: str
    sources: list[SourceCitation]
