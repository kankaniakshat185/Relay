from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.core.db import get_db
from relay_api.core.deps import CurrentUser
from relay_api.features.who_to_ask import service
from relay_api.features.who_to_ask.schemas import (
    DirectoryEntry,
    FileSearchMatch,
    RepoOption,
    WhoToAskRequest,
    WhoToAskResponse,
)

router = APIRouter(prefix="/who-to-ask", tags=["who-to-ask"])


@router.get("/repos", response_model=list[RepoOption])
async def list_repos(
    current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> list[RepoOption]:
    return await service.list_repos(db, current_user)


@router.get("/browse", response_model=list[DirectoryEntry])
async def browse(
    owner: str,
    repo: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    path: str = "",
) -> list[DirectoryEntry]:
    return await service.browse(db, current_user, owner, repo, path)


@router.get("/search", response_model=list[FileSearchMatch])
async def search(
    q: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[FileSearchMatch]:
    return await service.search_files(db, current_user, q)


@router.post("/rank", response_model=WhoToAskResponse)
async def rank(
    request: WhoToAskRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WhoToAskResponse:
    return await service.rank(
        db,
        current_user,
        owner=request.owner,
        repo=request.repo,
        ref=request.ref,
        path=request.path,
        strategy=request.strategy,
        target_type=request.target_type,
        pr_number=request.pr_number,
    )
