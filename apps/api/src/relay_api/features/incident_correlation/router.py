from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.core.db import get_db
from relay_api.core.deps import CurrentUser
from relay_api.features.incident_correlation import service
from relay_api.features.incident_correlation.schemas import (
    IncidentCorrelationRequest,
    IncidentCorrelationResponse,
)

router = APIRouter(prefix="/incident-correlation", tags=["incident-correlation"])


@router.post("", response_model=IncidentCorrelationResponse)
async def correlate(
    request: IncidentCorrelationRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IncidentCorrelationResponse:
    return await service.correlate(
        db,
        current_user,
        incident_at=request.incident_at,
        window_before_hours=request.window_before_hours,
        window_after_hours=request.window_after_hours,
        owner=request.owner,
        repo=request.repo,
        ref=request.ref,
        file_path=request.file_path,
        use_llm=request.use_llm,
        llm_provider=request.llm_provider,
        byok_api_key=request.api_key,
    )
