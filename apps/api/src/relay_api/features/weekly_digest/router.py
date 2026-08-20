from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.core.db import get_db
from relay_api.core.deps import CurrentUser
from relay_api.features.weekly_digest import service
from relay_api.features.weekly_digest.schemas import WeeklyDigestRequest, WeeklyDigestResponse

router = APIRouter(prefix="/weekly-digest", tags=["weekly-digest"])


@router.post("", response_model=WeeklyDigestResponse)
async def weekly_digest(
    request: WeeklyDigestRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WeeklyDigestResponse:
    return await service.build_digest(
        db,
        current_user,
        days=request.days,
        use_llm=request.use_llm,
        llm_provider=request.llm_provider,
        byok_api_key=request.api_key,
    )
