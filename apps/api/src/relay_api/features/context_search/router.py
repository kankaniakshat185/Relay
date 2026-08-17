from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.core.db import get_db
from relay_api.core.deps import CurrentUser
from relay_api.features.context_search import service
from relay_api.features.context_search.schemas import ContextSearchRequest, ContextSearchResponse

router = APIRouter(prefix="/context-search", tags=["context-search"])


@router.post("", response_model=ContextSearchResponse)
async def context_search(
    request: ContextSearchRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContextSearchResponse:
    return await service.search(db, current_user, request.query)
