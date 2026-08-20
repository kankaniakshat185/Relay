"""Connector (data-access) OAuth endpoints — distinct from `auth/router.py`'s
login OAuth (ADR 0003). Every route here requires an active login session
(`CurrentUser`) first; connecting a provider is something a signed-in user
does, never a way to sign in.

Routes (mounted under `/v1/connectors`):
  GET    ""                          — connection status for all providers
  GET    /{provider}/connect         — redirect to provider's consent screen
  GET    /{provider}/callback        — exchange code, store credential, kick off indexing
  POST   /{provider}/sync            — manually trigger a re-sync now
  DELETE /{provider}                 — disconnect
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.connectors import service
from relay_api.connectors.registry import get_connector_providers
from relay_api.connectors.schemas import ConnectorStatus
from relay_api.core.config import get_settings
from relay_api.core.db import get_db
from relay_api.core.deps import CurrentUser
from relay_api.core.logging import get_logger
from relay_api.jobs.indexing import index_connector_task

router = APIRouter(prefix="/connectors", tags=["connectors"])
logger = get_logger(__name__)

_STATE_COOKIE = "relay_connector_oauth_state"


def _redirect_uri(provider_name: str) -> str:
    settings = get_settings()
    return f"{settings.api_base_url}{settings.api_v1_prefix}/connectors/{provider_name}/callback"


@router.get("", response_model=list[ConnectorStatus])
async def list_connectors(
    current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> list[ConnectorStatus]:
    return await service.list_statuses(db, current_user.id)


@router.get("/{provider_name}/connect")
async def connect(provider_name: str, current_user: CurrentUser) -> Response:
    providers = get_connector_providers()
    provider = providers.get(provider_name)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown connector: {provider_name}")

    state = secrets.token_urlsafe(24)
    auth_url = provider.authorization_url(_redirect_uri(provider_name), state)

    settings = get_settings()
    response = RedirectResponse(auth_url, status_code=status.HTTP_302_FOUND)
    # Bind state to the logged-in user: the cookie proves "this browser
    # started this flow", the user id suffix proves it's still the same
    # session that started it by the time the callback comes back.
    response.set_cookie(
        _STATE_COOKIE,
        f"{state}:{current_user.id}",
        max_age=600,
        httponly=True,
        secure=settings.is_production,
        # See `auth/router.py`'s matching comment — "none" once deployed
        # (frontend/backend are genuinely different sites), "lax" locally.
        samesite="none" if settings.is_production else "lax",
    )
    return response


@router.get("/{provider_name}/callback")
async def callback(
    provider_name: str,
    code: str,
    state: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    oauth_state_cookie: Annotated[str | None, Cookie(alias=_STATE_COOKIE)] = None,
) -> Response:
    providers = get_connector_providers()
    provider = providers.get(provider_name)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown connector: {provider_name}")

    expected = f"{state}:{current_user.id}"
    if not oauth_state_cookie or oauth_state_cookie != expected:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state")

    account = await provider.exchange_code(code, _redirect_uri(provider_name))
    await service.upsert_credential(db, current_user.id, provider_name, account)
    logger.info(
        "connector_connected", extra={"user_id": str(current_user.id), "provider": provider_name}
    )

    index_connector_task.delay(str(current_user.id), provider_name)

    response = RedirectResponse(
        f"{get_settings().frontend_url}/connections", status_code=status.HTTP_302_FOUND
    )
    response.delete_cookie(_STATE_COOKIE)
    return response


@router.post("/{provider_name}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync(
    provider_name: str, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    """Manually triggers the same per-connector job the periodic 15-minute
    sweep runs (`jobs.indexing.index_connector_task`) — the fix for a
    user having no way to know their data might be stale, or to force a
    fresh sync, between automatic ticks. 202, not 200: this only *queues*
    the sync; the frontend polls `GET /v1/connectors` for `last_synced_at`
    moving to know it actually completed."""
    credential = await service.get_credential(db, current_user.id, provider_name)
    if credential is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{provider_name} is not connected")

    try:
        service.check_sync_allowed(credential)
    except service.SyncCooldownError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Synced recently — try again in {exc.retry_after_seconds}s.",
        ) from exc

    index_connector_task.delay(str(current_user.id), provider_name)
    logger.info(
        "connector_sync_triggered",
        extra={"user_id": str(current_user.id), "provider": provider_name},
    )


@router.delete("/{provider_name}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(
    provider_name: str, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    await service.delete_credential(db, current_user.id, provider_name)
