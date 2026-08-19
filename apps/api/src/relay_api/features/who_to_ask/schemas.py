from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RankingStrategy = Literal["recency", "frequency"]


class RepoOption(BaseModel):
    owner: str
    name: str
    full_name: str
    default_branch: str


class DirectoryEntry(BaseModel):
    name: str
    path: str
    type: Literal["file", "dir"]


class WhoToAskRequest(BaseModel):
    owner: str
    repo: str
    ref: str
    path: str
    strategy: RankingStrategy = "recency"


class PersonScore(BaseModel):
    author: str
    score: float
    touch_count: int
    last_touch_at: datetime
    sample_commit_urls: list[str]


class WhoToAskResponse(BaseModel):
    people: list[PersonScore]
    """Highest-scored first."""
    strategy_used: RankingStrategy
