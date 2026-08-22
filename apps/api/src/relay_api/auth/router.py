"""Login OAuth endpoints. Thin translation layer over `service.py`.

Routes (mounted under `/v1/auth`):
  GET  /{provider}/login     — redirect to provider's consent screen
  GET  /{provider}/callback  — exchange code, mint session, redirect to app
  POST /logout               — clear session cookie
  GET  /me                   — current user, 401 if not authenticated
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.providers import get_login_providers
from relay_api.auth.schemas import UserRead
from relay_api.auth.service import (
    build_authorization_url,
    exchange_code_for_identity,
    find_or_create_user,
    frontend_redirect_url,
)
from relay_api.core.config import get_settings
from relay_api.core.db import get_db
from relay_api.core.deps import CurrentUser
from relay_api.core.logging import get_logger
from relay_api.core.security import create_session_token

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)

_STATE_COOKIE = "relay_oauth_state"


def _redirect_uri(provider_name: str) -> str:
    # Points at the *frontend's* domain, proxied back to this route by
    # Next.js `rewrites()` (see `apps/web/next.config.ts`) — not this
    # service's own domain. That's what makes the session cookie set below
    # genuinely first-party: the browser never talks to the backend
    # directly, so from its perspective every request (including this
    # callback) stays on one site. See ADR 0024 for the full BFF-proxy
    # writeup and why `SameSite=None` (below) was a workaround, not a fix.
    settings = get_settings()
    return f"{settings.frontend_url}/api{settings.api_v1_prefix}/auth/{provider_name}/callback"


@router.get("/{provider_name}/login")
async def login(provider_name: str) -> Response:
    providers = get_login_providers()
    provider = providers.get(provider_name)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown login provider: {provider_name}")

    auth_url, state = build_authorization_url(provider, _redirect_uri(provider_name))

    settings = get_settings()
    response = RedirectResponse(auth_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        _STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=settings.is_production,
        # "lax" unconditionally — the browser only ever talks to
        # `frontend_url` (see `_redirect_uri` above), so this is genuinely
        # same-site even in production, not the cross-site case `None`
        # used to work around.
        samesite="lax",
    )
    return response


@router.get("/{provider_name}/callback")
async def callback(
    provider_name: str,
    code: str,
    state: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    oauth_state_cookie: Annotated[str | None, Cookie(alias=_STATE_COOKIE)] = None,
) -> Response:
    providers = get_login_providers()
    provider = providers.get(provider_name)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown login provider: {provider_name}")

    if not oauth_state_cookie or state != oauth_state_cookie:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state")

    identity = await exchange_code_for_identity(provider, code, _redirect_uri(provider_name))
    user = await find_or_create_user(db, provider_name, identity)
    logger.info("user_logged_in", extra={"user_id": str(user.id), "provider": provider_name})

    session_token = create_session_token(user.id)
    settings = get_settings()

    response = RedirectResponse(frontend_redirect_url("/"), status_code=status.HTTP_302_FOUND)
    response.delete_cookie(_STATE_COOKIE)
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=settings.session_token_ttl_seconds,
        httponly=True,
        secure=settings.is_production,
        # See the matching comment in `login()` above — this is the
        # cookie `lib/api.ts`'s `apiFetch` depends on for every subsequent
        # authenticated request, not just the redirect that sets it. Safe
        # as "lax" because every one of those requests goes through the
        # frontend's own `/api` proxy, never straight to this domain.
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(get_settings().session_cookie_name)
    return response


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
