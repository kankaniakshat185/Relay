"""Flaky Test Investigator endpoints (mounted under `/v1/flaky-tests`):
GET /repos      — repos available to pick from (same shape as
                  Archaeology/Who Should I Ask's own `/repos`)
GET /workflows  — per-workflow flakiness verdicts for one repo
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.core.db import get_db
from relay_api.core.deps import CurrentUser
from relay_api.features.flaky_tests import service
from relay_api.features.flaky_tests.schemas import RepoOption, WorkflowVerdict

router = APIRouter(prefix="/flaky-tests", tags=["flaky-tests"])


@router.get("/repos", response_model=list[RepoOption])
async def list_repos(
    current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> list[RepoOption]:
    return await service.list_repos(db, current_user)


@router.get("/workflows", response_model=list[WorkflowVerdict])
async def workflows(
    owner: str,
    repo: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[WorkflowVerdict]:
    return await service.analyze_workflows(db, current_user, f"{owner}/{repo}")
