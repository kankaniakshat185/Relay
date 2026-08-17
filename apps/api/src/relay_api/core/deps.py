"""Shared FastAPI dependencies (current user, etc.)."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.auth.service import get_user_by_id
from relay_api.core.config import get_settings
from relay_api.core.db import get_db
from relay_api.core.security import InvalidSessionToken, verify_session_token

settings = get_settings()


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    session_token: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> User:
    if session_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    try:
        user_id = verify_session_token(session_token)
    except InvalidSessionToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session") from exc

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
