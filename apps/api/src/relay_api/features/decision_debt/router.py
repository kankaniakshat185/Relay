from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.core.db import get_db
from relay_api.core.deps import CurrentUser
from relay_api.features.decision_debt import service
from relay_api.features.decision_debt.schemas import DecisionDebtRequest, DecisionDebtResponse

router = APIRouter(prefix="/decision-debt", tags=["decision-debt"])


@router.post("/scan", response_model=DecisionDebtResponse)
async def scan(
    request: DecisionDebtRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DecisionDebtResponse:
    return await service.scan(
        db,
        current_user,
        owner=request.owner,
        repo=request.repo,
        min_discussion_items=request.min_discussion_items,
        inactive_after_days=request.inactive_after_days,
    )
